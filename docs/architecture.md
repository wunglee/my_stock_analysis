# DSA 项目架构分析

> 本文档描述 DSA（Daily Stock Analysis）股票智能分析系统的整体架构、模块关系和数据流。
> 更新时间：2026-05-02

---

## 1. 项目定位

**DSA** 是一个覆盖 A股、港股、美股的股票智能分析系统。

**核心流程**：

```
数据抓取 → 技术分析/新闻检索 → LLM 分析 → 生成报告 → 多渠道通知推送
```

**交付形态**：

- **命令行工具**：`python main.py` 直接运行分析
- **FastAPI 服务**：`python main.py --serve` 提供 REST API
- **Web 前端**：`apps/dsa-web/`（React 19 + Vite）
- **桌面端**：`apps/dsa-desktop/`（Electron + 打包 Python 后端）
- **定时任务**：GitHub Actions 每日自动运行
- **Docker 部署**：支持定时模式和 API 服务模式

---

## 2. 项目结构总览

```
daily_stock_analysis/
├── main.py                    # CLI 入口（分析、定时、完整流程）
├── server.py                  # FastAPI 服务入口
├── analyzer_service.py        # 多调用方统一的分析 API 封装
├── webui.py                   # Web UI 入口
│
├── src/                       # 后端核心源码
│   ├── core/                  # 主流程编排
│   ├── services/              # 业务服务层
│   ├── repositories/          # 数据访问层（Repository Pattern）
│   ├── schemas/               # Pydantic Schema
│   ├── agent/                 # 多智能体系统
│   ├── notification_sender/   # 通知发送器（11 种渠道）
│   ├── storage.py             # SQLite ORM / DatabaseManager
│   ├── config.py              # 全局配置（单例）
│   ├── auth.py                # 认证模块
│   └── enums.py               # 枚举类型
│
├── data_provider/             # 多数据源适配（Strategy Pattern）
│   ├── base.py                # Fetcher 基类 + 管理器 + 熔断器
│   ├── efinance_fetcher.py    # 东方财富（A股首选）
│   ├── akshare_fetcher.py     # AkShare（多子源聚合）
│   ├── tushare_fetcher.py     # Tushare Pro
│   ├── yfinance_fetcher.py    # Yahoo Finance（美股）
│   ├── longbridge_fetcher.py  # 长桥 OpenAPI（港股/美股）
│   ├── tickflow_fetcher.py    # 市场复盘专用
│   ├── fundamental_adapter.py # 基本面适配器
│   └── realtime_types.py      # 实时行情统一类型定义
│
├── api/                       # FastAPI API
│   ├── app.py                 # 应用工厂
│   └── v1/endpoints/          # 路由端点
│
├── apps/
│   ├── dsa-web/               # Web 前端（React 19 + Vite）
│   └── dsa-desktop/           # 桌面端（Electron + 打包 Python）
│
├── strategies/                # YAML 策略定义（12 种策略）
├── tests/                     # pytest 测试套件
├── scripts/                   # 本地脚本
├── docker/                    # Docker 构建
├── .github/workflows/         # GitHub Actions CI/CD
└── docs/                      # 文档
```

---

## 3. 数据流全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          数据流全景图                                    │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │Efinance(东方)│  │   AkShare    │  │  Tushare Pro │  │   Yahoo Fin. │
  │  A股首选    │  │  多源聚合    │  │  高质量API   │  │  美股兜底    │
  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
         │                 │                 │                 │
  ┌──────┴─────────────────┴─────────────────┴─────────────────┴──────┐
  │                    DataFetcherManager                              │
  │         策略模式 + 按优先级自动故障切换 + 熔断器保护                 │
  │  美股: YFinance → Longbridge                                       │
  │  港股: Longbridge → AkShare                                        │
  │  A股: Efinance → AkShare → Tushare → Pytdx → Baostock             │
  └──────┬───────────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │ UnifiedRealtime  │  │  历史K线(ORM)    │  │ ChipDistribution │
  │   统一实时行情    │  │  StockDaily      │  │    筹码分布      │
  └──────┬───────────┘  └──────┬───────────┘  └──────┬───────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
              ┌─────────────────────────────┐
              │    StockAnalysisPipeline    │
              │      (src/core/pipeline)    │
              │  - 断点续传检查              │
              │  - 数据获取与保存            │
              │  - 趋势分析（本地计算）       │
              │  - 情报搜索（多搜索引擎）     │
              │  - LLM 分析 / Agent 流水线   │
              └────────────┬────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │  传统分析路径 │ │ Agent分析路径│ │  回测评估路径 │
     │ Gemini/Claude│ │ 多智能体编排 │ │ BacktestEngine│
     │ 直接 LLM 调用│ │ Orchestrator │ │              │
     └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
            │                │                │
            ▼                ▼                ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │ AnalysisReport││OrchestratorResult││BacktestResult│
     │  结构化报告   │ │ 决策仪表盘 JSON│ │   评估结果    │
     └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
            │                │                │
            └────────────────┼────────────────┘
                             ▼
              ┌─────────────────────────────┐
              │    NotificationService      │
              │    (11 种通知渠道并发推送)   │
              │  - Markdown → 图片转换       │
              │  - 企业微信/飞书/Telegram   │
              │  - Discord/Slack/邮件/推送   │
              └─────────────────────────────┘
```

---

## 4. 后端分层架构

### 4.1 Repository 层 — 数据访问抽象

采用 **Repository Pattern**，将数据库操作封装在标准接口后，业务逻辑依赖抽象接口，不依赖具体存储机制。

```
src/repositories/
├── stock_repo.py      # 股票数据 CRUD、分析上下文查询
├── analysis_repo.py   # 分析历史记录查询与保存
├── backtest_repo.py   # 回测候选获取、结果批量保存
└── portfolio_repo.py  # 持仓数据 CRUD
```

### 4.2 Service 层 — 业务逻辑

```
src/services/
├── analysis_service.py   # 封装分析逻辑，统一 CLI/Bot/API 入口
├── backtest_service.py   # 回测编排：批量获取候选 → 引擎评估 → 持久化
├── portfolio_service.py  # 持仓账户、交易记录、现金流管理
├── history_service.py    # 历史数据服务
├── task_service.py       # 任务调度与管理
├── report_renderer.py    # 报告渲染（Markdown/HTML/图片）
└── image_stock_extractor.py  # 图片中的股票代码提取（LLM + 正则）
```

### 4.3 Core 层 — 流程编排

```
src/core/
├── pipeline.py           # 股票分析主流程调度器（1775行）
├── backtest_engine.py    # 回测引擎（纯逻辑，DB无关）
├── market_review.py      # 每日大盘复盘
├── market_analyzer.py    # 大盘分析器
├── market_strategy.py    # 区域化市场策略蓝图（CN/US/HK）
├── trading_calendar.py   # 多市场交易日历
└── config_manager.py     # 配置管理器
```

**`StockAnalysisPipeline`** 核心流程：

1. 检查断点续传（今日是否已分析）
2. 获取历史K线数据（`DataFetcherManager`）
3. 本地技术指标计算（MA/MACD/RSI）
4. 新闻情报搜索（多搜索引擎并发）
5. LLM 分析（传统直接调用 **或** Agent 流水线）
6. 生成结构化报告（Pydantic Schema 校验）
7. 保存结果到 SQLite
8. 发送通知（Markdown → 图片 → 多渠道并发推送）

---

## 5. 多数据源适配层

### 5.1 Fetcher 策略模式

**基类**：`data_provider/base.py` 中的 `BaseFetcher`

```python
class BaseFetcher(ABC):
    @abstractmethod
    def _fetch_raw_data(self, stock_code, start, end):
        """获取原始数据"""

    @abstractmethod
    def _normalize_data(self, raw_data):
        """标准化为标准列名：date, open, high, low, close, volume, amount, pct_chg"""
```

### 5.2 所有 Fetcher

| Fetcher | 文件 | 优先级 | 定位 |
|---------|------|--------|------|
| EfinanceFetcher | `efinance_fetcher.py` | 0 | A股首选（东方财富） |
| AkshareFetcher | `akshare_fetcher.py` | 1 | A股主数据源（多子源） |
| TushareFetcher | `tushare_fetcher.py` | 0/2 | 有Token时P0，否则P2 |
| PytdxFetcher | `pytdx_fetcher.py` | 2 | 通达信行情服务器 |
| BaostockFetcher | `baostock_fetcher.py` | 3 | 证券宝备用 |
| YfinanceFetcher | `yfinance_fetcher.py` | 4 | Yahoo Finance 兜底 |
| LongbridgeFetcher | `longbridge_fetcher.py` | 5 | 长桥OpenAPI（美股/港股） |
| TickFlowFetcher | `tickflow_fetcher.py` | 99 | 仅市场复盘 |

### 5.3 按市场路由

| 市场 | 数据源优先级 | 特殊处理 |
|------|-------------|---------|
| **A股** | Efinance → AkShare → Tushare → Pytdx → Baostock | 涨跌停规则：北交所30%、科创/创业板20%、ST股5%、普通10% |
| **港股** | Longbridge → AkShare(hk) | 代码格式：`HK00700` |
| **美股** | YFinance → Longbridge | 指数映射：`SPX` → `^GSPC`，`DJI` → `^DJI` |

### 5.4 Fallback 机制

1. **历史数据 Fallback**：按优先级遍历 Fetcher，单源失败自动切换下一源
2. **实时行情 Fallback**：主源成功但缺少量比/换手率等字段时，继续从后续源补充
3. **熔断器保护**：
   - 实时行情：连续3次失败 → 熔断5分钟
   - 筹码分布：连续2次失败 → 熔断10分钟
4. **防封禁**：随机休眠（1.5-5秒）、随机 User-Agent、tenacity 指数退避重试

### 5.5 实时行情统一类型

```python
# data_provider/realtime_types.py
@dataclass
class UnifiedRealtimeQuote:
    price: float          # 当前价
    change_pct: float     # 涨跌幅
    volume: int           # 成交量
    volume_ratio: float   # 量比
    turnover_rate: float  # 换手率
    pe_ratio: float       # PE
    pb_ratio: float       # PB
    # ... 30+ 个统一字段
```

---

## 6. LLM 集成架构

### 6.1 多 Provider 统一调用

通过 **LiteLLM** 统一调用：

| Provider | 配置变量 |
|---------|---------|
| Google Gemini | `GEMINI_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Anthropic Claude | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| AIHubMix | `AIHUBMIX_KEY` |
| Ollama（本地） | `OLLAMA_BASE_URL` |

### 6.2 多模型 Fallback 链

主模型失败时自动尝试 fallback 模型链，直到成功或全部失败。

### 6.3 结构化输出

```python
# src/schemas/report_schema.py
class AnalysisReportSchema(BaseModel):
    core_conclusion: CoreConclusion      # 核心结论（信号/置信度/理由）
    data_perspective: DataPerspective    # 数据视角（趋势/价格/量能/筹码）
    intelligence: Intelligence           # 情报（新闻/风险/催化）
    battle_plan: BattlePlan              # 作战计划（狙击点/仓位/检查清单）
```

---

## 7. 多智能体系统（Agent System）

### 7.1 智能体类型

```
src/agent/agents/
├── base_agent.py        # Agent 抽象基类（LLM 调用、工具使用、上下文管理）
├── technical_agent.py   # 技术分析智能体（均线/MACD/RSI/形态）
├── intel_agent.py       # 情报搜集智能体（新闻/公告/资金流）
├── risk_agent.py        # 风险筛查智能体（减持/业绩/监管）
├── decision_agent.py    # 决策合成智能体（最终仪表盘，无工具）
└── portfolio_agent.py   # 持仓分析智能体
```

### 7.2 编排器模式

```
src/agent/orchestrator.py  # 多智能体流水线协调器
```

支持 4 种模式：

| 模式 | 流水线 | LLM 调用次数 |
|------|--------|-------------|
| `quick` | Technical → Decision | ~2 次 |
| `standard` | Technical → Intel → Decision | ~3 次（默认） |
| `full` | Technical → Intel → Risk → Decision | ~4 次 |
| `specialist` | Technical → Intel → Risk → Specialist → Decision | ~5 次 |

### 7.3 通信协议

```python
# src/agent/protocols.py
@dataclass
class AgentContext:
    query: str = ""
    stock_code: str = ""
    data: Dict[str, Any] = field(default_factory=dict)       # 共享数据
    opinions: List[AgentOpinion] = field(default_factory=list)  # 各智能体意见
    risk_flags: List[Dict] = field(default_factory=list)     # 风险标记

@dataclass
class AgentOpinion:
    agent_name: str
    signal: str           # strong_buy / buy / hold / sell / strong_sell
    confidence: float     # 0.0-1.0
    reasoning: str
    key_levels: Dict[str, float]
```

### 7.4 工具系统

```
src/agent/tools/
├── registry.py          # 工具注册表（OpenAI function calling schema）
├── data_tools.py        # 数据工具（行情/K线/筹码/基本面）
├── analysis_tools.py    # 分析工具（趋势/技术指标）
├── search_tools.py      # 搜索工具（新闻/多搜索引擎）
├── market_tools.py      # 市场工具（大盘/板块）
└── backtest_tools.py    # 回测工具
```

### 7.5 技能系统（YAML 驱动策略）

```
strategies/
├── bull_trend.yaml          # 默认多头趋势
├── ma_golden_cross.yaml     # 均线金叉
├── volume_breakout.yaml     # 放量突破
├── dragon_head.yaml         # 龙头策略
├── shrink_pullback.yaml     # 缩量回踩
├── bottom_volume.yaml       # 底部放量
├── one_yang_three_yin.yaml  # 一阳夹三阴
├── box_oscillation.yaml     # 箱体震荡
├── chan_theory.yaml         # 缠论
├── wave_theory.yaml         # 波浪理论
└── emotion_cycle.yaml       # 情绪周期
```

每个策略 YAML 包含：名称、分类、所需工具、适配的市场状态标签、自然语言策略说明。用户可自定义策略，无需编写代码。

---

## 8. 通知系统

### 8.1 架构

```python
# src/notification.py — 多继承聚合所有发送器
class NotificationService(
    AstrbotSender, CustomWebhookSender, DiscordSender,
    EmailSender, FeishuSender, PushoverSender,
    PushplusSender, Serverchan3Sender, SlackSender,
    TelegramSender, WechatSender
):
```

### 8.2 支持渠道

| 渠道 | 配置变量 |
|------|---------|
| 企业微信 | `WECHAT_WEBHOOK_URL` |
| 飞书 | `FEISHU_WEBHOOK_URL` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| 邮件 SMTP | `EMAIL_HOST`, `EMAIL_USER`, `EMAIL_PASSWORD` |
| Discord | `DISCORD_WEBHOOK_URL` |
| Slack | `SLACK_WEBHOOK_URL` |
| Pushover | `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY` |
| PushPlus | `PUSHPLUS_TOKEN` |
| Server酱3 | `SERVERCHAN3_SENDKEY` |
| ASTRBOT | `ASTRBOT_WEBHOOK_URL` |
| 自定义 Webhook | `CUSTOM_WEBHOOK_URLS` |

**设计原则**：单渠道失败不拖垮整体，Markdown 报告先转图片再推送。

---

## 9. Web 前端架构（apps/dsa-web）

### 9.1 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | React | 19.2.0 |
| 构建 | Vite | ~6.0 |
| 语言 | TypeScript | ~5.7 |
| 路由 | react-router-dom | 7.13.0 |
| 状态管理 | Zustand + React Context | 5.0.11 |
| 样式 | Tailwind CSS | 4.1.18 |
| HTTP | Axios | 1.13.4 |
| 图表 | Recharts | 3.3.0 |
| 实时通信 | EventSource (SSE) + fetch stream | 原生 API |
| 测试 | Playwright | ~1.49 |

### 9.2 路由结构

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | `HomePage.tsx` | 股票分析仪表盘、历史记录、报告查看 |
| `/chat` | `ChatPage.tsx` | AI 多轮对话、技能选择、会话管理 |
| `/portfolio` | `PortfolioPage.tsx` | 持仓账户管理、交易记录、风险分析 |
| `/backtest` | `BacktestPage.tsx` | 策略回测、结果筛选、绩效指标 |
| `/settings` | `SettingsPage.tsx` | 系统配置、LLM 通道、认证设置 |
| `/login` | `LoginPage.tsx` | 登录/首次设置 |

### 9.3 状态管理

```
Zustand Store（高频业务状态）
├── stockPoolStore.ts    # 首页仪表盘状态（查询/历史/报告/任务）
├── agentChatStore.ts    # AI 对话状态（消息/会话/流式输出）
└── analysisStore.ts     # 分析任务状态

React Context（低频认证状态）
└── AuthContext.tsx      # 认证状态 + 自动初始化 + 路由守卫
```

### 9.4 实时通信

| 机制 | 场景 | 实现 |
|------|------|------|
| SSE | 任务实时状态流 | `EventSource` → `/api/v1/analysis/tasks/stream` |
| fetch stream | AI 对话流式输出 | 原生 `fetch` + `ReadableStream` + `AbortController` |
| 轮询 | 历史记录刷新 | `setInterval(30000ms)` + `visibilitychange` 事件 |

### 9.5 认证流程

1. `AuthContext` 挂载时自动请求 `GET /api/v1/auth/status`
2. `setupState === 'no_password'` → 首次设置密码
3. `setupState === 'password_retained'` → 登录
4. 基于 **HTTP-only Cookie**，前端不存储 Token
5. 任何 401 → 自动跳转 `/login?redirect=当前路径`

---

## 10. 桌面端架构（apps/dsa-desktop）

### 10.1 核心定位

Electron 包装器 + 打包 Python 后端，不是"纯前端包装"：

```
Electron main.js 启动
    ↓
显示 loading.html（加载动画）
    ↓
动态寻找可用端口（8000-8100）
    ↓
spawn Python 后端（PyInstaller 可执行文件 / python main.py）
    ↓
轮询 /api/health 直到就绪（最多60秒）
    ↓
加载 Web UI（http://127.0.0.1:{port}/）
    ↓
Web UI 由 FastAPI 的 static 文件处理器服务
```

### 10.2 桌面专属能力

| 能力 | 实现 |
|------|------|
| 自动启动后端 | Electron 进程管理（spawn/monitor/kill） |
| 版本更新检查 | GitHub Releases API 比对 |
| 配置备份/恢复 | `/api/system-config/desktop-export`（`DSA_DESKTOP_MODE` 限制） |
| 本地数据 | `.env` + `data/stock_analysis.db` + `logs/` 都在可执行文件旁 |
| 主题感知 | `nativeTheme` 适配暗色/亮色 |

### 10.3 与 Web 版对比

| 维度 | Web | Desktop |
|------|-----|---------|
| 后端 | 需手动启动 | 自动 spawn |
| 数据库 | 服务器端 | 本地 SQLite |
| 配置 | 环境变量 | 本地 `.env` 文件 |
| 更新 | 服务器部署 | GitHub Release 检查 |
| 端口 | Vite 5173 | FastAPI 8000-8100 |

---

## 11. CI/CD 与部署

### 11.1 CI 流水线

| Job | 触发条件 | 说明 | 阻断 |
|-----|---------|------|------|
| `ai-governance` | 所有 PR | 校验 AGENTS.md / CLAUDE.md / Copilot 指令 | 是 |
| `backend-gate` | 所有 PR | `./scripts/ci_gate.sh`：语法 → Flake8 → 测试 | 是 |
| `docker-build` | 所有 PR | Docker 构建 + 关键模块导入 smoke | 是 |
| `web-gate` | Web 改动时 | `npm run lint && npm run build` | 是 |

### 11.2 发布流程

```
commit message 含 #patch/#minor/#major
    ↓
auto-tag.yml → 自动 bump 版本号
    ↓
push annotated tag vX.Y.Z
    ↓
create-release.yml → 创建 GitHub Release
docker-publish.yml → 推送多架构镜像（linux/amd64, linux/arm64）
desktop-release.yml → Windows .exe + macOS .dmg
```

### 11.3 每日定时任务

- **调度**：工作日 UTC 10:00（北京时间 18:00）
- **随机延迟**：0-60 秒（防并发冲突）
- **超时**：30 分钟
- **产物**：`reports/` + `logs/` 作为 artifact 保留 30 天

### 11.4 Docker 部署

```yaml
# docker/docker-compose.yml
services:
  analyzer:  # 定时任务模式
    command: python main.py --schedule
  server:    # API 服务模式
    command: python main.py --serve-only
    ports: ["8000:8000"]
```

多阶段构建：Stage 1（Node）构建 Web UI → Stage 2（Python 3.11 slim）运行后端。

---

## 12. 关键设计模式

| 模式 | 应用位置 | 价值 |
|------|---------|------|
| **Repository Pattern** | `src/repositories/` | 数据访问抽象，便于测试和切换存储 |
| **Strategy Pattern** | `data_provider/` | 多数据源 + 自动故障切换 |
| **Circuit Breaker** | `data_provider/realtime_types.py` | 防止连续失败时反复请求，自动恢复 |
| **Multi-Agent Orchestration** | `src/agent/orchestrator.py` | 专业智能体流水线，支持 4 种模式 |
| **YAML-Driven Skills** | `strategies/` | 用户可自定义策略，无需编写代码 |
| **Fail-Open** | `data_provider/fundamental_adapter.py` | 基本面数据允许部分返回，不拖垮整体 |
| **Layered Architecture** | `src/` 三层 | Repository → Service → Core，职责清晰 |
| **MVC/MVVM（前端）** | `apps/dsa-web/` | Pages → Components → Hooks → Stores 分层 |

---

## 13. 技术债务与注意事项

1. **前端 `index.css` 过大**：约 2900 行 CSS，建议拆分为按功能域的 CSS 模块
2. **桌面端 `main.js` 过长**：约 1040 行，可考虑按功能拆分为模块
3. **`pipeline.py` 过长**：1775 行，是核心调度器但已接近维护边界
4. **单测覆盖率**：测试文件数量多但需关注覆盖率是否达到目标
5. **Bundle 体积**：Vite 构建产物 JS 约 1.2MB（gzip 后 394KB），可考虑代码分割优化

---

*本文档由架构探索自动生成，后续迭代中如有模块新增或架构调整，请及时更新。*
