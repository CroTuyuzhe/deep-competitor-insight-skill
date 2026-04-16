#!/usr/bin/env python3
"""
竞品深度分析 - LangGraph StateGraph 实现

工作流:
  START → intent_understanding → industry_landscape → product_screening → product_deep_dive
    ├─ (有聚焦维度) → dimension_focus_analysis → user_pain_point_mining
    └─ (无聚焦维度) → user_pain_point_mining
    → competitor_comparison → key_insight_extraction
    ├─ (deep/strategic) → trend_prediction → strategic_report → END
    └─ (basic/standard) → strategic_report → END
"""

from __future__ import annotations

import argparse
import json
import operator
import re
import sys
from datetime import datetime
from typing import Annotated, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from web_search import (
    batch_search,
    collect_sources,
    extract_numbers_with_units,
    extract_product_names,
    extract_snippets,
    search_bilingual,
    search_news,
    search_web,
)


# ============================================================
# 行业关键词映射
# ============================================================

INDUSTRY_KEYWORDS = {
    "AI陪伴": {"en": "AI companion", "aliases": ["ai陪伴", "AI伴侣", "虚拟陪伴", "AI角色扮演", "AI聊天"]},
    "AI编程": {"en": "AI coding assistant", "aliases": ["AI代码", "AI编程助手", "代码补全"]},
    "AI写作": {"en": "AI writing", "aliases": ["AI文案", "AI内容生成"]},
    "AI绘画": {"en": "AI image generation", "aliases": ["AI画图", "AI生图", "文生图"]},
    "AI视频": {"en": "AI video generation", "aliases": ["AI生成视频", "文生视频"]},
    "AI搜索": {"en": "AI search engine", "aliases": ["AI搜索引擎", "智能搜索"]},
    "AI教育": {"en": "AI education", "aliases": ["AI学习", "AI辅导", "智能教育"]},
    "AI医疗": {"en": "AI healthcare", "aliases": ["AI健康", "智能医疗"]},
    "AI客服": {"en": "AI customer service", "aliases": ["智能客服", "AI对话"]},
    "短视频": {"en": "short video", "aliases": ["短视频平台"]},
    "社交": {"en": "social media", "aliases": ["社交平台", "社交媒体"]},
    "电商": {"en": "e-commerce", "aliases": ["电商平台", "网购"]},
    "在线教育": {"en": "online education", "aliases": ["在线学习", "网课"]},
    "SaaS": {"en": "SaaS", "aliases": ["企业服务", "云服务"]},
    "游戏": {"en": "gaming", "aliases": ["手游", "网游"]},
    "直播": {"en": "live streaming", "aliases": ["直播平台"]},
    "知识付费": {"en": "knowledge commerce", "aliases": ["付费课程", "内容付费"]},
    "协同办公": {"en": "collaboration tools", "aliases": ["在线协作", "办公工具"]},
    "大模型": {"en": "large language model", "aliases": ["LLM", "基础模型", "大语言模型"]},
}

DEPTH_KEYWORDS = {
    "strategic": ["战略", "战略级", "全面战略", "strategic"],
    "deep": ["深度", "深入", "详细", "详尽", "全链路", "deep"],
    "basic": ["简要", "简单", "概览", "快速", "basic"],
}

FOCUS_PATTERNS = [
    r'(会员[体系设计功能付费]*)',
    r'(付费[转化模式设计策略]*)',
    r'(商业[模式化策略]*)',
    r'(增长[策略模式引擎]*)',
    r'(获客[渠道策略模式]*)',
    r'(内容[生态体系策略]*)',
    r'(交互[体验设计]*)',
    r'(技术[架构壁垒方案]*)',
    r'(定价[策略模式体系]*)',
    r'(运营[策略模式体系]*)',
    r'(用户[体验留存增长]*)',
    r'(算法[推荐机制]*)',
    r'(社区[运营生态]*)',
    r'(变现[模式策略]*)',
]


# ============================================================
# 状态定义
# ============================================================

class CompetitorAnalysisState(TypedDict):
    # 输入/配置
    query: str
    industry: Optional[str]
    industry_en: Optional[str]
    scope: Optional[str]                          # "全面" | "聚焦" | "对比"
    depth: Optional[str]                          # "basic" | "standard" | "deep" | "strategic"
    focus_dimension: Optional[str]
    output_type: Optional[str]                    # "report" | "comparison" | "brief"
    market_region: Optional[str]                  # "cn" | "global" | "both"
    max_products: int
    intent_config: Optional[Dict]

    # 节点2: 行业全景
    landscape_data: Optional[Dict]
    landscape_sources: Optional[List[str]]

    # 节点3: 产品筛选
    products: Optional[List[Dict]]
    screening_sources: Optional[List[str]]

    # 节点4: 产品深挖
    product_profiles: Optional[List[Dict]]
    deep_dive_sources: Optional[List[str]]

    # 节点5: 维度聚焦 (条件)
    has_focus_dimension: bool
    dimension_analysis: Optional[Dict]
    dimension_sources: Optional[List[str]]

    # 节点6: 用户痛点
    pain_points: Optional[Dict]
    pain_point_sources: Optional[List[str]]

    # 节点7: 竞品对比
    comparison_matrix: Optional[Dict]
    comparison_summary: Optional[str]

    # 节点8: 关键洞察
    insights: Optional[Dict]

    # 节点9: 趋势预测 (条件)
    include_trends: bool
    trends: Optional[Dict]
    trend_sources: Optional[List[str]]

    # 节点10: 最终报告
    report_json: Optional[Dict]
    report_text: Optional[str]

    # 元数据
    errors: Annotated[List[str], operator.add]
    timestamp: Optional[str]
    verbose: bool
    search_count: Annotated[int, operator.add]


# ============================================================
# 节点函数
# ============================================================

def node_intent_understanding(state: CompetitorAnalysisState) -> Dict:
    """节点1: 解析用户查询，提取行业/范围/深度/聚焦维度"""
    verbose = state.get("verbose", False)
    if verbose:
        print("\n[节点1] 意图解析...")

    query = state.get("query", "")
    errors = []

    # 解析行业
    industry = state.get("industry")
    industry_en = state.get("industry_en")
    if not industry:
        for ind, info in INDUSTRY_KEYWORDS.items():
            if ind.lower() in query.lower():
                industry = ind
                industry_en = info["en"]
                break
            for alias in info.get("aliases", []):
                if alias.lower() in query.lower():
                    industry = ind
                    industry_en = info["en"]
                    break
            if industry:
                break

    if not industry:
        # 尝试从 query 中提取行业关键词
        m = re.search(r'(?:分析|调研|研究|了解)(?:一下)?(.{2,8}?)(?:行业|赛道|领域|市场|产品|竞品)', query)
        if m:
            industry = m.group(1).strip()
            industry_en = industry  # 作为 fallback
        else:
            industry = query[:10]
            industry_en = industry
            errors.append("未能精确识别行业，使用查询前缀作为行业名")

    if not industry_en:
        industry_en = INDUSTRY_KEYWORDS.get(industry, {}).get("en", industry)

    # 解析深度
    depth = state.get("depth") or "standard"
    if depth == "standard":
        for d, keywords in DEPTH_KEYWORDS.items():
            for kw in keywords:
                if kw in query.lower():
                    depth = d
                    break
            if depth != "standard":
                break

    # 解析聚焦维度
    focus = state.get("focus_dimension")
    if not focus:
        for pattern in FOCUS_PATTERNS:
            m = re.search(pattern, query)
            if m:
                focus = m.group(1)
                break

    # 解析范围
    scope = "全面"
    if focus:
        scope = "聚焦"
    elif "对比" in query or "vs" in query.lower():
        scope = "对比"

    # 解析市场区域
    region = state.get("market_region") or "both"
    if "国内" in query and "海外" not in query and "国外" not in query:
        region = "cn"
    elif ("海外" in query or "国外" in query or "全球" in query) and "国内" not in query:
        region = "global"

    # 输出类型
    output_type = "report"
    if "表格" in query or "对比表" in query:
        output_type = "comparison"
    elif "简要" in query or "概览" in query:
        output_type = "brief"

    intent_config = {
        "industry": industry,
        "industry_en": industry_en,
        "scope": scope,
        "depth": depth,
        "focus_dimension": focus,
        "market_region": region,
        "output_type": output_type,
        "original_query": query,
    }

    if verbose:
        print(f"  行业: {industry} ({industry_en})")
        print(f"  范围: {scope}")
        print(f"  深度: {depth}")
        print(f"  聚焦维度: {focus or '无'}")
        print(f"  市场区域: {region}")
        print(f"  输出类型: {output_type}")

    return {
        "industry": industry,
        "industry_en": industry_en,
        "scope": scope,
        "depth": depth,
        "focus_dimension": focus,
        "market_region": region,
        "output_type": output_type,
        "has_focus_dimension": focus is not None,
        "include_trends": depth in ("deep", "strategic"),
        "intent_config": intent_config,
        "errors": errors,
    }


def node_industry_landscape(state: CompetitorAnalysisState) -> Dict:
    """节点2: 行业全景 - 市场规模/格局/赛道分层"""
    verbose = state.get("verbose", False)
    industry = state.get("industry", "")
    industry_en = state.get("industry_en", "")
    region = state.get("market_region", "both")
    depth = state.get("depth", "standard")

    if verbose:
        print(f"\n[节点2] 行业全景: {industry}...")

    errors = []
    all_results = []
    sources = []
    search_count = 0

    # 构建搜索查询
    queries_cn = [
        f"{industry} 行业市场规模 2024 2025",
        f"{industry} 行业竞争格局 玩家分布",
        f"{industry} 赛道分层 细分市场",
    ]
    queries_en = [
        f"{industry_en} market size 2024 2025",
        f"{industry_en} industry landscape competition",
    ]

    if depth in ("deep", "strategic"):
        queries_cn.append(f"{industry} 行业发展历程 融资")
        queries_en.append(f"{industry_en} industry growth funding")

    # 执行搜索
    if region in ("cn", "both"):
        for q in queries_cn:
            results = search_web(q, max_results=6, region="wt-wt")
            all_results.extend(results)
            search_count += 1

    if region in ("global", "both"):
        for q in queries_en:
            results = search_web(q, max_results=6, region="us-en")
            all_results.extend(results)
            search_count += 1

    if not all_results:
        errors.append("行业全景数据获取失败")

    # 提取结构化数据
    text = extract_snippets(all_results, max_chars=5000)
    numbers = extract_numbers_with_units(text)
    sources = collect_sources(all_results)

    landscape_data = {
        "industry": industry,
        "raw_snippets": text,
        "market_numbers": numbers,
        "key_players_mentioned": extract_product_names(all_results),
        "result_count": len(all_results),
    }

    if verbose:
        print(f"  搜索 {search_count} 次, 获取 {len(all_results)} 条结果")
        print(f"  提取到 {len(numbers)} 个数字指标")
        print(f"  提及的玩家: {', '.join(landscape_data['key_players_mentioned'][:10])}")

    return {
        "landscape_data": landscape_data,
        "landscape_sources": sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_product_screening(state: CompetitorAnalysisState) -> Dict:
    """节点3: 产品筛选 - 识别头部/代表性竞品"""
    verbose = state.get("verbose", False)
    industry = state.get("industry", "")
    industry_en = state.get("industry_en", "")
    region = state.get("market_region", "both")
    max_products = state.get("max_products", 8)
    landscape_players = (state.get("landscape_data") or {}).get("key_players_mentioned", [])

    if verbose:
        print(f"\n[节点3] 产品筛选 (最多 {max_products} 个)...")

    errors = []
    all_results = []
    search_count = 0

    queries_cn = [
        f"{industry} 头部产品 排名 APP",
        f"{industry} 主要竞品 有哪些 产品",
        f"{industry} 知名产品 用户量",
    ]
    queries_en = [
        f"{industry_en} top products apps ranking 2024",
        f"{industry_en} competitors list market share",
    ]

    if region in ("cn", "both"):
        for q in queries_cn:
            results = search_web(q, max_results=6, region="wt-wt")
            all_results.extend(results)
            search_count += 1

    if region in ("global", "both"):
        for q in queries_en:
            results = search_web(q, max_results=6, region="us-en")
            all_results.extend(results)
            search_count += 1

    # 提取产品名
    product_names = extract_product_names(all_results, known_patterns=landscape_players)
    text = extract_snippets(all_results, max_chars=4000)

    # 构建产品列表
    products = []
    seen = set()
    for name in product_names[:max_products * 2]:
        if name in seen or len(name) < 2:
            continue
        seen.add(name)
        # 判断国内外
        is_cn = any('\u4e00' <= c <= '\u9fff' for c in name)
        products.append({
            "name": name,
            "region": "cn" if is_cn else "global",
            "brief_desc": "",
            "source_mentions": 1,
        })
        if len(products) >= max_products:
            break

    sources = collect_sources(all_results)

    if not products:
        errors.append("未能从搜索结果中筛选出具体产品")

    if verbose:
        print(f"  搜索 {search_count} 次, 获取 {len(all_results)} 条结果")
        print(f"  筛选出 {len(products)} 个产品:")
        for p in products:
            print(f"    - {p['name']} ({p['region']})")

    return {
        "products": products,
        "screening_sources": sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_product_deep_dive(state: CompetitorAnalysisState) -> Dict:
    """节点4: 产品深挖 - 每个产品的定位/功能/商业模式"""
    verbose = state.get("verbose", False)
    products = state.get("products") or []
    industry = state.get("industry", "")
    depth = state.get("depth", "standard")

    if verbose:
        print(f"\n[节点4] 产品深度分析 ({len(products)} 个产品)...")

    errors = []
    profiles = []
    all_sources = []
    search_count = 0

    for product in products:
        name = product["name"]
        is_cn = product.get("region") == "cn"

        if verbose:
            print(f"  分析: {name}...")

        product_results = []

        # 基本搜索: 定位 + 功能
        q1 = f"{name} 产品定位 核心功能 特色" if is_cn else f"{name} product features positioning"
        results = search_web(q1, max_results=5, region="wt-wt" if is_cn else "us-en")
        product_results.extend(results)
        search_count += 1

        # 商业模式
        q2 = f"{name} 商业模式 盈利 收费" if is_cn else f"{name} business model revenue pricing"
        results = search_web(q2, max_results=5, region="wt-wt" if is_cn else "us-en")
        product_results.extend(results)
        search_count += 1

        # 深度模式: 用户数据
        if depth in ("deep", "strategic"):
            q3 = f"{name} 用户数 DAU 融资" if is_cn else f"{name} users DAU funding"
            results = search_web(q3, max_results=3, region="wt-wt" if is_cn else "us-en")
            product_results.extend(results)
            search_count += 1

        text = extract_snippets(product_results, max_chars=2000)
        numbers = extract_numbers_with_units(text)

        profile = {
            "name": name,
            "region": product.get("region", "unknown"),
            "raw_snippets": text,
            "market_numbers": numbers,
            "search_result_count": len(product_results),
        }
        profiles.append(profile)
        all_sources.extend(collect_sources(product_results))

    if verbose:
        print(f"  总搜索 {search_count} 次, 构建了 {len(profiles)} 个产品档案")

    return {
        "product_profiles": profiles,
        "deep_dive_sources": all_sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_dimension_focus_analysis(state: CompetitorAnalysisState) -> Dict:
    """节点5: 维度聚焦分析 - 针对用户指定的维度深度分析"""
    verbose = state.get("verbose", False)
    focus = state.get("focus_dimension", "")
    industry = state.get("industry", "")
    industry_en = state.get("industry_en", "")
    products = state.get("products") or []

    if verbose:
        print(f"\n[节点5] 维度聚焦分析: {focus}...")

    errors = []
    all_results = []
    search_count = 0

    # 行业层面搜索
    queries = [
        f"{industry} {focus} 分析 对比",
        f"{industry} {focus} 最佳实践 案例",
    ]
    for q in queries:
        results = search_web(q, max_results=6, region="wt-wt")
        all_results.extend(results)
        search_count += 1

    # 英文搜索
    focus_en = focus  # 简单 fallback
    q_en = f"{industry_en} {focus_en} analysis best practices"
    results = search_web(q_en, max_results=5, region="us-en")
    all_results.extend(results)
    search_count += 1

    # 头部产品的维度搜索
    top_products = products[:3]
    for p in top_products:
        q = f"{p['name']} {focus}"
        results = search_web(q, max_results=4, region="wt-wt")
        all_results.extend(results)
        search_count += 1

    text = extract_snippets(all_results, max_chars=4000)
    sources = collect_sources(all_results)

    dimension_analysis = {
        "dimension": focus,
        "raw_snippets": text,
        "products_analyzed": [p["name"] for p in top_products],
        "result_count": len(all_results),
    }

    if verbose:
        print(f"  搜索 {search_count} 次, 获取 {len(all_results)} 条结果")

    return {
        "dimension_analysis": dimension_analysis,
        "dimension_sources": sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_user_pain_point_mining(state: CompetitorAnalysisState) -> Dict:
    """节点6: 用户痛点挖掘 - 真实用户吐槽/不满/潜在需求"""
    verbose = state.get("verbose", False)
    industry = state.get("industry", "")
    industry_en = state.get("industry_en", "")
    products = state.get("products") or []
    depth = state.get("depth", "standard")

    if verbose:
        print(f"\n[节点6] 用户痛点挖掘...")

    errors = []
    all_results = []
    search_count = 0

    # 行业通用痛点
    queries_cn = [
        f"{industry} 用户吐槽 缺点 问题",
        f"{industry} 用户评价 不满意 差评",
    ]
    queries_en = [
        f"{industry_en} user complaints problems reddit",
    ]

    for q in queries_cn:
        results = search_web(q, max_results=6, region="wt-wt")
        all_results.extend(results)
        search_count += 1

    for q in queries_en:
        results = search_web(q, max_results=5, region="us-en")
        all_results.extend(results)
        search_count += 1

    # 头部产品痛点
    if depth in ("deep", "strategic"):
        for p in products[:3]:
            q = f"{p['name']} 差评 问题 bug 缺点"
            results = search_web(q, max_results=4, region="wt-wt")
            all_results.extend(results)
            search_count += 1

    text = extract_snippets(all_results, max_chars=4000)
    sources = collect_sources(all_results)

    pain_points = {
        "raw_snippets": text,
        "result_count": len(all_results),
        "products_checked": [p["name"] for p in products[:3]],
    }

    if verbose:
        print(f"  搜索 {search_count} 次, 获取 {len(all_results)} 条结果")

    return {
        "pain_points": pain_points,
        "pain_point_sources": sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_competitor_comparison(state: CompetitorAnalysisState) -> Dict:
    """节点7: 竞品对比 - 多维度对比矩阵"""
    verbose = state.get("verbose", False)
    industry = state.get("industry", "")
    products = state.get("products") or []

    if verbose:
        print(f"\n[节点7] 竞品对比矩阵...")

    errors = []
    all_results = []
    search_count = 0

    # 行业对比搜索
    q = f"{industry} 竞品对比 分析 2024"
    results = search_web(q, max_results=6, region="wt-wt")
    all_results.extend(results)
    search_count += 1

    # 头部产品 vs 搜索
    if len(products) >= 2:
        q = f"{products[0]['name']} vs {products[1]['name']} 对比"
        results = search_web(q, max_results=5, region="wt-wt")
        all_results.extend(results)
        search_count += 1

    text = extract_snippets(all_results, max_chars=3000)
    sources = collect_sources(all_results)

    # 构建对比矩阵框架
    dimensions = [
        "目标用户", "核心功能", "商业模式", "定价策略",
        "技术路线", "内容生态", "用户体量", "差异化",
    ]

    matrix = {
        "dimensions": dimensions,
        "products": [p["name"] for p in products],
        "raw_comparison_data": text,
        "result_count": len(all_results),
    }

    if verbose:
        print(f"  搜索 {search_count} 次")
        print(f"  对比维度: {len(dimensions)} 个")
        print(f"  对比产品: {len(products)} 个")

    return {
        "comparison_matrix": matrix,
        "comparison_summary": text[:500],
        "search_count": search_count,
        "errors": errors,
    }


def node_key_insight_extraction(state: CompetitorAnalysisState) -> Dict:
    """节点8: 关键洞察提炼 - 从所有数据中提取核心洞察"""
    verbose = state.get("verbose", False)

    if verbose:
        print(f"\n[节点8] 关键洞察提炼...")

    # 汇总所有收集到的数据
    landscape = state.get("landscape_data") or {}
    profiles = state.get("product_profiles") or []
    pain_points = state.get("pain_points") or {}
    comparison = state.get("comparison_matrix") or {}
    dimension = state.get("dimension_analysis") or {}

    # 提取洞察框架
    insights = {
        "data_summary": {
            "total_products_analyzed": len(profiles),
            "industry": state.get("industry", ""),
            "landscape_data_available": bool(landscape.get("raw_snippets")),
            "pain_points_data_available": bool(pain_points.get("raw_snippets")),
            "dimension_analysis_available": bool(dimension.get("raw_snippets")),
            "comparison_data_available": bool(comparison.get("raw_comparison_data")),
        },
        "all_market_numbers": landscape.get("market_numbers", []),
        "products_overview": [
            {
                "name": p.get("name"),
                "region": p.get("region"),
                "data_richness": len(p.get("raw_snippets", "")),
                "numbers_found": len(p.get("market_numbers", [])),
            }
            for p in profiles
        ],
        "pain_point_text": pain_points.get("raw_snippets", ""),
        "comparison_text": comparison.get("raw_comparison_data", ""),
        "dimension_text": dimension.get("raw_snippets", ""),
    }

    if verbose:
        print(f"  汇总 {len(profiles)} 个产品档案")
        print(f"  市场数据点: {len(insights['all_market_numbers'])} 个")

    return {
        "insights": insights,
        "errors": [],
    }


def node_trend_prediction(state: CompetitorAnalysisState) -> Dict:
    """节点9: 趋势预测 - 功能/用户/商业化趋势"""
    verbose = state.get("verbose", False)
    industry = state.get("industry", "")
    industry_en = state.get("industry_en", "")

    if verbose:
        print(f"\n[节点9] 趋势预测...")

    errors = []
    all_results = []
    search_count = 0

    queries_cn = [
        f"{industry} 未来趋势 2025 2026 预测",
        f"{industry} 技术发展方向 创新",
    ]
    queries_en = [
        f"{industry_en} trends 2025 2026 predictions",
        f"{industry_en} future technology roadmap",
    ]

    for q in queries_cn:
        results = search_web(q, max_results=6, region="wt-wt")
        all_results.extend(results)
        search_count += 1

    for q in queries_en:
        results = search_web(q, max_results=5, region="us-en")
        all_results.extend(results)
        search_count += 1

    # 新闻搜索补充
    news = search_news(f"{industry} 最新动态 趋势", max_results=5)
    all_results.extend(news)
    search_count += 1

    text = extract_snippets(all_results, max_chars=4000)
    sources = collect_sources(all_results)

    trends = {
        "raw_snippets": text,
        "result_count": len(all_results),
        "news_count": len(news),
    }

    if verbose:
        print(f"  搜索 {search_count} 次, 获取 {len(all_results)} 条结果")
        print(f"  其中新闻 {len(news)} 条")

    return {
        "trends": trends,
        "trend_sources": sources,
        "search_count": search_count,
        "errors": errors,
    }


def node_strategic_report(state: CompetitorAnalysisState) -> Dict:
    """节点10: 编译最终报告 JSON"""
    verbose = state.get("verbose", False)
    if verbose:
        print(f"\n[节点10] 编译战略报告...")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 计算总搜索次数
    total_searches = state.get("search_count", 0)

    # 汇编所有来源
    all_sources = []
    for key in ["landscape_sources", "screening_sources", "deep_dive_sources",
                "dimension_sources", "pain_point_sources", "trend_sources"]:
        src = state.get(key)
        if src:
            all_sources.extend(src)

    # 去重来源
    seen = set()
    unique_sources = []
    for s in all_sources:
        if s not in seen:
            seen.add(s)
            unique_sources.append(s)

    report_json = {
        "meta": {
            "query": state.get("query", ""),
            "industry": state.get("industry", ""),
            "industry_en": state.get("industry_en", ""),
            "depth": state.get("depth", "standard"),
            "scope": state.get("scope", "全面"),
            "focus_dimension": state.get("focus_dimension"),
            "market_region": state.get("market_region", "both"),
            "timestamp": ts,
            "total_products_analyzed": len(state.get("products") or []),
            "total_searches": total_searches,
            "errors": state.get("errors", []),
        },
        "intent": state.get("intent_config"),
        "landscape": state.get("landscape_data"),
        "products": state.get("products"),
        "product_profiles": state.get("product_profiles"),
        "dimension_analysis": state.get("dimension_analysis"),
        "pain_points": state.get("pain_points"),
        "comparison": state.get("comparison_matrix"),
        "insights": state.get("insights"),
        "trends": state.get("trends"),
        "sources": unique_sources[:50],
    }

    # 生成文本草稿
    lines = []
    lines.append("=" * 60)
    lines.append(f"  竞品深度分析报告: {state.get('industry', '')}")
    lines.append(f"  {ts}")
    lines.append("=" * 60)

    lines.append(f"\n查询: {state.get('query', '')}")
    lines.append(f"深度: {state.get('depth', 'standard')}")
    lines.append(f"聚焦: {state.get('focus_dimension') or '全面分析'}")
    lines.append(f"区域: {state.get('market_region', 'both')}")
    lines.append(f"产品数: {len(state.get('products') or [])}")
    lines.append(f"搜索次数: {total_searches}")

    # 产品列表
    products = state.get("products") or []
    if products:
        lines.append("\n分析产品:")
        for i, p in enumerate(products, 1):
            lines.append(f"  {i}. {p['name']} ({p.get('region', '')})")

    # 数据摘要
    landscape = state.get("landscape_data") or {}
    if landscape.get("market_numbers"):
        lines.append(f"\n市场数据点: {len(landscape['market_numbers'])} 个")

    # 错误
    errs = state.get("errors", [])
    if errs:
        lines.append("\n⚠ 警告:")
        for e in errs:
            lines.append(f"  - {e}")

    lines.append("\n" + "=" * 60)
    lines.append("完整数据请查看 JSON 输出")
    lines.append("基于以上数据，Claude 将生成深度洞察报告")
    lines.append("=" * 60)

    report_text = "\n".join(lines)

    if verbose:
        print(f"  报告已编译: {len(unique_sources)} 个来源")

    return {
        "report_json": report_json,
        "report_text": report_text,
        "timestamp": ts,
        "errors": [],
    }


# ============================================================
# 路由函数
# ============================================================

def route_after_deep_dive(state: CompetitorAnalysisState) -> str:
    """条件路由1: 有聚焦维度 → 维度分析; 无 → 直接痛点挖掘"""
    if state.get("has_focus_dimension", False):
        return "dimension_focus_analysis"
    return "user_pain_point_mining"


def route_after_insights(state: CompetitorAnalysisState) -> str:
    """条件路由2: 深度/战略级 → 趋势预测; 否则 → 直接报告"""
    if state.get("include_trends", False):
        return "trend_prediction"
    return "strategic_report"


# ============================================================
# 图构建
# ============================================================

def build_graph() -> StateGraph:
    """构建 LangGraph StateGraph"""
    graph = StateGraph(CompetitorAnalysisState)

    # 添加节点
    graph.add_node("intent_understanding", node_intent_understanding)
    graph.add_node("industry_landscape", node_industry_landscape)
    graph.add_node("product_screening", node_product_screening)
    graph.add_node("product_deep_dive", node_product_deep_dive)
    graph.add_node("dimension_focus_analysis", node_dimension_focus_analysis)
    graph.add_node("user_pain_point_mining", node_user_pain_point_mining)
    graph.add_node("competitor_comparison", node_competitor_comparison)
    graph.add_node("key_insight_extraction", node_key_insight_extraction)
    graph.add_node("trend_prediction", node_trend_prediction)
    graph.add_node("strategic_report", node_strategic_report)

    # 线性边
    graph.set_entry_point("intent_understanding")
    graph.add_edge("intent_understanding", "industry_landscape")
    graph.add_edge("industry_landscape", "product_screening")
    graph.add_edge("product_screening", "product_deep_dive")

    # 条件路由1: 产品深挖后
    graph.add_conditional_edges(
        "product_deep_dive",
        route_after_deep_dive,
        {
            "dimension_focus_analysis": "dimension_focus_analysis",
            "user_pain_point_mining": "user_pain_point_mining",
        },
    )
    graph.add_edge("dimension_focus_analysis", "user_pain_point_mining")

    graph.add_edge("user_pain_point_mining", "competitor_comparison")
    graph.add_edge("competitor_comparison", "key_insight_extraction")

    # 条件路由2: 关键洞察后
    graph.add_conditional_edges(
        "key_insight_extraction",
        route_after_insights,
        {
            "trend_prediction": "trend_prediction",
            "strategic_report": "strategic_report",
        },
    )
    graph.add_edge("trend_prediction", "strategic_report")

    graph.add_edge("strategic_report", END)

    return graph


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="竞品深度分析 (LangGraph)")
    parser.add_argument("--query", "-q", type=str, required=True,
                        help="分析查询 (如: 'AI陪伴行业竞品分析')")
    parser.add_argument("--industry", "-i", type=str, default=None,
                        help="指定行业 (覆盖自动解析)")
    parser.add_argument("--depth", "-d",
                        choices=["basic", "standard", "deep", "strategic"],
                        default="standard",
                        help="分析深度 (default: standard)")
    parser.add_argument("--focus", type=str, default=None,
                        help="聚焦维度 (如: '会员设计', '商业模式')")
    parser.add_argument("--region", choices=["cn", "global", "both"],
                        default="both",
                        help="市场区域 (default: both)")
    parser.add_argument("--format", "-f", choices=["text", "json"],
                        default="json",
                        help="输出格式 (default: json)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示每个节点的执行详情")
    parser.add_argument("--max-products", type=int, default=8,
                        help="最大分析产品数 (default: 8)")
    args = parser.parse_args()

    if args.verbose:
        print("=" * 60)
        print("  竞品深度分析 - LangGraph StateGraph")
        print("=" * 60)

    # 构建并编译图
    graph = build_graph()
    app = graph.compile()

    if args.verbose or args.format == "text":
        print("\n📊 分析流程图:\n")
        app.get_graph().print_ascii()

    # 初始状态
    initial_state = {
        "query": args.query,
        "industry": args.industry,
        "industry_en": None,
        "scope": None,
        "depth": args.depth,
        "focus_dimension": args.focus,
        "output_type": None,
        "market_region": args.region,
        "max_products": args.max_products,
        "intent_config": None,
        "landscape_data": None,
        "landscape_sources": None,
        "products": None,
        "screening_sources": None,
        "product_profiles": None,
        "deep_dive_sources": None,
        "has_focus_dimension": args.focus is not None,
        "dimension_analysis": None,
        "dimension_sources": None,
        "pain_points": None,
        "pain_point_sources": None,
        "comparison_matrix": None,
        "comparison_summary": None,
        "insights": None,
        "include_trends": args.depth in ("deep", "strategic"),
        "trends": None,
        "trend_sources": None,
        "report_json": None,
        "report_text": None,
        "errors": [],
        "timestamp": None,
        "verbose": args.verbose,
        "search_count": 0,
    }

    # 执行图
    if args.verbose:
        print("\n开始分析...\n")
    result = app.invoke(initial_state)

    # 输出
    if args.format == "json":
        output = result.get("report_json", {})
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(result.get("report_text", "报告生成失败"))


if __name__ == "__main__":
    main()
