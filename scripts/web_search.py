"""
竞品分析 - 数据采集层
DuckDuckGo 搜索封装，中英文双语查询，重试逻辑，结果提取工具
"""

from __future__ import annotations

import re
import time
import warnings
from typing import Dict, List, Optional, Set

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ============================================================
# 限速控制
# ============================================================

_last_search_time = 0.0


def _rate_limit(min_interval: float = 1.0):
    """确保搜索请求之间的最小间隔"""
    global _last_search_time
    elapsed = time.time() - _last_search_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_search_time = time.time()


# ============================================================
# 核心搜索函数
# ============================================================

def _get_ddgs():
    """获取 DDGS 实例，优先使用 ddgs 包，回退到 duckduckgo_search"""
    try:
        from ddgs import DDGS
        return DDGS()
    except ImportError:
        from duckduckgo_search import DDGS
        return DDGS()


def search_web(query: str, max_results: int = 8, retries: int = 3,
               region: str = "cn-zh") -> List[Dict]:
    """
    DuckDuckGo 文本搜索，带重试和指数退避。
    返回: [{title, href, body}, ...]
    """
    for attempt in range(retries):
        try:
            _rate_limit(min_interval=1.0)
            ddgs = _get_ddgs()
            results = list(ddgs.text(
                query, region=region, max_results=max_results
            ))
            return results
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    return []


def search_news(query: str, max_results: int = 5, retries: int = 3,
                region: str = "cn-zh") -> List[Dict]:
    """
    DuckDuckGo 新闻搜索。
    返回: [{title, url, body, date, source}, ...]
    """
    for attempt in range(retries):
        try:
            _rate_limit(min_interval=1.0)
            ddgs = _get_ddgs()
            results = list(ddgs.news(
                query, region=region, max_results=max_results
            ))
            return results
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    return []


def search_bilingual(query_cn: str, query_en: str,
                     max_results_per: int = 5) -> Dict:
    """
    执行中英文双语搜索，URL 去重，返回合并结果。
    返回: {cn_results: [...], en_results: [...], combined: [...]}
    """
    cn_results = search_web(query_cn, max_results=max_results_per, region="wt-wt")
    en_results = search_web(query_en, max_results=max_results_per, region="us-en")

    seen_urls: Set[str] = set()
    combined = []
    for r in cn_results + en_results:
        url = r.get("href", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined.append(r)

    return {
        "cn_results": cn_results,
        "en_results": en_results,
        "combined": combined,
    }


# ============================================================
# 结果处理工具
# ============================================================

def extract_snippets(results: List[Dict], max_chars: int = 3000) -> str:
    """
    将搜索结果的标题+摘要拼接为文本，用于数据提取。
    超过 max_chars 截断。
    """
    parts = []
    total = 0
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        snippet = f"【{title}】{body}"
        if total + len(snippet) > max_chars:
            remaining = max_chars - total
            if remaining > 50:
                parts.append(snippet[:remaining])
            break
        parts.append(snippet)
        total += len(snippet)
    return "\n".join(parts)


def extract_product_names(results: List[Dict],
                          known_patterns: Optional[List[str]] = None) -> List[str]:
    """
    从搜索结果中提取产品/品牌名称。
    使用已知产品名匹配 + 中文书名号/引号提取。
    """
    text = extract_snippets(results, max_chars=5000)
    names: List[str] = []
    seen: Set[str] = set()

    # 匹配已知产品名
    if known_patterns:
        for pattern in known_patterns:
            if pattern in text and pattern not in seen:
                names.append(pattern)
                seen.add(pattern)

    # 提取中文书名号内容: 《产品名》
    for m in re.finditer(r'[《「]([^》」]{2,15})[》」]', text):
        name = m.group(1).strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)

    # 提取中文产品名模式: "XX APP"、"XX 助手"、"XX AI" 等
    cn_product_suffixes = r'(?:APP|App|app|助手|AI|智能体|机器人|平台|工具|引擎|大模型|伴侣|陪聊)'
    cn_skip = {"中国", "全球", "国内", "国外", "市场", "行业", "日报", "新闻", "公司",
               "报告", "分析", "评测", "排名", "用户", "功能", "技术", "数据", "论文",
               "人形机器人", "聊天机器人", "客服机器人", "写作工具", "对话助手"}
    for m in re.finditer(rf'([\u4e00-\u9fff\w]{{2,8}}{cn_product_suffixes})', text):
        name = m.group(1).strip()
        if (name and name not in seen and name not in cn_skip
                and len(name) >= 3 and not any(s in name for s in ("从", "年", "是", "最"))):
            names.append(name)
            seen.add(name)

    # 提取英文产品名 (带 AI/App 等产品特征词的组合)
    product_patterns = [
        r'\b([A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*){0,2}\s*(?:AI|App|Chat|Bot|GPT|Pro|Plus))\b',
        r'\b((?:AI|Chat|Deep|Open)\s*[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\b',
    ]
    skip = {
        "The", "This", "That", "What", "How", "Why", "Top", "Best", "New",
        "For", "And", "With", "From", "Google", "Search", "About", "About Us",
        "Mobile App", "Web App", "Read More", "Learn More", "Sign Up",
        "Log In", "Contact Us", "Privacy Policy", "Terms", "Home",
        "Visual Coding Meets", "Agent Swarm", "Chat History", "More Info",
        "Free Trial", "Get Started", "See More", "View All", "Click Here",
        "Download Now", "Try Free", "Our Products", "Our Services",
        "Microsoft", "Apple", "Amazon", "Facebook", "Meta",
    }
    for pattern in product_patterns:
        for m in re.finditer(pattern, text):
            name = m.group(1).strip()
            if name not in skip and name not in seen and len(name) > 2:
                names.append(name)
                seen.add(name)

    return names


def extract_numbers_with_units(text: str) -> List[Dict]:
    """
    从文本中提取带单位的数字: 市场规模、用户数、增长率等。
    返回: [{value, unit, context}, ...]
    """
    results = []

    # 中文: X亿元、X万人、X%
    cn_patterns = [
        (r'(\d+\.?\d*)\s*亿[元美]', '亿元'),
        (r'(\d+\.?\d*)\s*万亿', '万亿'),
        (r'(\d+\.?\d*)\s*万[人用户]', '万人'),
        (r'(\d+\.?\d*)\s*亿[人用户]', '亿人'),
        (r'(\d+\.?\d*)%', '%'),
        (r'(\d+\.?\d*)\s*[万千百]万', '万'),
    ]
    for pattern, unit in cn_patterns:
        for m in re.finditer(pattern, text):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            context = text[start:end].strip()
            results.append({
                "value": m.group(1),
                "unit": unit,
                "context": context,
            })

    # 英文: $X billion, X million users
    en_patterns = [
        (r'\$(\d+\.?\d*)\s*billion', '$B'),
        (r'\$(\d+\.?\d*)\s*million', '$M'),
        (r'(\d+\.?\d*)\s*million\s*users', 'M users'),
        (r'(\d+\.?\d*)\s*billion\s*users', 'B users'),
        (r'(\d+\.?\d*)%', '%'),
    ]
    for pattern, unit in en_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            context = text[start:end].strip()
            results.append({
                "value": m.group(1),
                "unit": unit,
                "context": context,
            })

    return results


def collect_sources(results: List[Dict]) -> List[str]:
    """从搜索结果中提取来源 URL 列表"""
    sources = []
    for r in results:
        url = r.get("href", r.get("url", ""))
        title = r.get("title", "")
        if url:
            sources.append(f"{title} ({url})" if title else url)
    return sources


def batch_search(queries: List[str], max_results_per: int = 5,
                 region: str = "cn-zh") -> Dict:
    """
    批量执行多个搜索查询，返回合并结果。
    返回: {all_results: [...], per_query: {query: [results]}, sources: [...]}
    """
    all_results = []
    per_query = {}
    for q in queries:
        results = search_web(q, max_results=max_results_per, region=region)
        per_query[q] = results
        all_results.extend(results)

    return {
        "all_results": all_results,
        "per_query": per_query,
        "sources": collect_sources(all_results),
    }
