# Deep Competitor Insight Skill

互联网/科技行业竞品深度分析工具，基于 LangGraph 状态机 + DuckDuckGo 双语搜索，输出结构化数据供 AI 生成专业级竞品报告。

## 工作流

```
START
  │
  ▼
[意图解析] 解析行业/范围/深度/聚焦维度
  │
  ▼
[行业全景] 搜索市场规模/格局/赛道分层
  │
  ▼
[产品筛选] 识别头部/代表性/垂直/海外产品
  │
  ▼
[产品深挖] 每个产品的定位/功能/商业模式/差异
  │
  ├─ 有聚焦维度 → [维度深度分析]
  │                    │
  └─ 无聚焦维度 ──┐    │
                  ▼    ▼
              [用户痛点挖掘]
                  │
                  ▼
              [竞品对比] 多维度对比矩阵
                  │
                  ▼
              [关键洞察] 竞争规律/壁垒/机会
                  │
                  ├─ deep/strategic → [趋势预测]
                  │                        │
                  └─ basic/standard ──┐    │
                                     ▼    ▼
                                 [战略报告]
                                     │
                                     ▼
                                    END
```

10 个节点，2 个条件路由分支，覆盖从意图理解到战略报告的完整分析链路。

## 快速开始

### 安装依赖

```bash
pip install ddgs langgraph
```

### 命令行使用

```bash
cd scripts

# 标准分析
python3 competitor_analysis.py --query "AI陪伴行业竞品分析" --depth standard

# 深度分析 + 指定聚焦维度
python3 competitor_analysis.py --query "短视频行业竞品分析" --depth deep --focus "商业模式"

# 战略级分析 + JSON输出
python3 competitor_analysis.py \
  --query "AI编程助手赛道分析" \
  --depth strategic \
  --region both \
  --format json \
  --verbose
```

### 作为 Claude Code Skill 使用

将本仓库放入 `~/.claude/skills/` 目录下即可自动注册。触发词：

- "竞品分析"、"竞争分析"、"行业分析"、"竞品对比"
- "分析XX行业"、"XX赛道分析"
- "帮我做竞品调研"、"competitive analysis"

Claude 会自动运行脚本采集数据，然后基于 JSON 输出生成 9 章节专业报告。

## CLI 参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--query` | `-q` | 用户查询（必填） | - |
| `--industry` | `-i` | 指定行业（覆盖自动解析） | 自动解析 |
| `--depth` | `-d` | 分析深度：basic / standard / deep / strategic | standard |
| `--focus` | | 聚焦维度（如"会员设计"、"定价策略"） | 无 |
| `--region` | | 市场区域：cn / global / both | both |
| `--format` | `-f` | 输出格式：json / text | json |
| `--verbose` | `-v` | 显示节点执行详情 | 关闭 |
| `--max-products` | | 最大分析产品数 | 8 |

### 深度说明

| 深度 | 搜索量 | 适用场景 |
|------|--------|---------|
| basic | ~20次 | 快速概览，了解赛道大致格局 |
| standard | ~25次 | 日常竞品调研，产品对比 |
| deep | ~35次 | 深度调研，包含趋势预测 |
| strategic | ~45次 | 战略级分析，给老板汇报用 |

## 报告结构

脚本输出结构化 JSON，配合 Claude 生成 9 大章节报告：

1. **行业全景** — 市场规模、增速、赛道分层
2. **竞品矩阵总览** — 产品定位图、tier 划分
3. **产品深度拆解** — 每个产品的战略逻辑
4. **聚焦维度分析** — 跨产品横向对比（条件触发）
5. **用户痛点与机会** — 痛点→机会映射
6. **多维度对比表** — 格式化对比矩阵
7. **核心洞察** — 3-5 条非显而易见的战略洞察
8. **趋势预测** — 6-12 个月格局变化预判（deep/strategic）
9. **战略建议** — 可执行建议，关联具体证据

## 架构

```
deep-competitor-insight-skill/
├── SKILL.md                      # Claude Code Skill 配置 + 报告生成指南
├── requirements.txt              # ddgs, langgraph
├── README.md
├── LICENSE
└── scripts/
    ├── competitor_analysis.py    # LangGraph 主图：10节点 + 2条件路由 + CLI
    └── web_search.py             # DuckDuckGo 搜索封装：重试、限速、双语、提取
```

- **数据采集层** (`web_search.py`)：DuckDuckGo 中英文双语搜索，带重试和限速，结果提取（产品名、数字指标、摘要）
- **分析引擎层** (`competitor_analysis.py`)：LangGraph StateGraph，10 个节点按序执行，2 个条件路由动态调整流程
- **报告生成层** (`SKILL.md`)：Claude 基于 JSON 数据进行深度推理，生成有洞察的专业报告

核心设计原则：**数据来自脚本，洞察来自 AI 推理。**

## 数据源

- **搜索引擎**：DuckDuckGo（无需 API key）
- **搜索策略**：每节点 3-6 次搜索，中英文双语覆盖
- **数据处理**：正则提取产品名、市场数字（亿元/$B/%）、URL 去重

## 注意事项

- 搜索数据来自公开网络，可能存在时效性和准确性限制
- 洞察和趋势判断基于 AI 推理，非确定性结论
- 若 DuckDuckGo 搜索受限，部分节点可能数据不足，报告会标注
- 结论仅供研究参考，重大商业决策请结合更多信源验证

## License

[MIT](LICENSE)
