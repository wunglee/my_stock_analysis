# 纯算法技术面回测系统设计文档

> 状态：设计稿（待确认）
> 范围：与现有 AI 回测完全独立的新模块

---

## 1. 目标与范围

### 1.1 核心目标

构建一个**纯算法、无 LLM** 的技术面回测系统，用于：
- 从纯 K 线 + 成交量中统计发现概率规律
- 多股同测，发现联动 / 共振 / 滞后关系
- 用算法信号替代 AI 建议，验证规律有效性
- 输出独立文件，供图形化展示

### 1.2 与现有系统的边界

| 维度 | 现有 AI 回测 | 纯算法回测（本系统） |
|------|-------------|---------------------|
| 输入 | `analysis_history` + 实时数据 | 历史 K 线 + 成交量 |
| 决策来源 | LLM 分析建议 | 纯算法规则 |
| 筹码分布 | 实时数据源 | 日成交量推断 |
| 输出存储 | 数据库 (`backtest_result`) | 独立 JSON 文件 |
| 多股支持 | 单股串行 | 多股并行 + 跨股分析 |
| 回测周期 | 基于已有记录日期 | 用户指定日期范围 |

**硬性约束**：不改任何已有代码，新模块完全独立。

---

## 2. 架构设计

### 2.1 模块结构

```
src/core/technical_backtest/
├── __init__.py
├── data_loader.py          # 历史 K 线加载（复用 history_loader）
├── chip_estimator.py       # 日成交量推断筹码分布
├── indicators.py           # 技术指标计算（MA/MACD/RSI/量价等）
├── rule_discovery.py       # 规则发现算法
├── signal_generator.py     # 纯算法交易信号生成
├── backtest_runner.py      # 回测执行引擎
├── cross_stock.py          # 多股共振/联动分析
├── output_writer.py        # 结果输出到独立文件
└── models.py               # 数据模型（dataclass）

api/routers/
└── technical_backtest.py   # FastAPI 路由（独立）
```

### 2.2 数据流

```
用户请求（股票列表 + 日期范围 + 步长）
         ↓
[数据加载]  history_loader.load_history_df() → 多股 K 线 DataFrame
         ↓
[指标计算]  计算 MA/MACD/RSI/量能/筹码（每只股票独立）
         ↓
[规则发现]  统计规律：均线支撑率 / 量价分布 / 形态胜率
         ↓
[信号生成]  基于规则生成每日交易信号（买/卖/持有/观望）
         ↓
[回测验证]  用后续 N 天实际走势验证信号准确性
         ↓
[跨股分析]  多股相关系数 / 领先滞后关系
         ↓
[文件输出]  JSON 文件（含规则、信号、验证结果、跨股关系）
         ↓
[前端展示]  图形化展示（标注规律、绘制共振图）
```

---

## 3. 核心模块设计

### 3.1 数据加载（data_loader.py）

复用 `src/services/history_loader.py` 的 `load_history_df()`，支持：
- DB 优先加载（已有历史 K 线）
- 网络回退（DB 缺失时从数据源拉取）
- 多股批量加载（并行）

```python
def load_multi_stock_dfs(
    codes: List[str],
    start_date: date,
    end_date: date,
) -> Dict[str, pd.DataFrame]:
    """加载多只股票的历史 K 线，返回 {code: df} 字典。"""
```

### 3.2 筹码分布估算（chip_estimator.py）

**核心假设**：无分时数据时，假设当日成交均匀分布在 `[low, high]` 区间。

**算法**：

```
输入：历史 K 线 DataFrame（含 open/high/low/close/volume）
输出：每日筹码分布（获利比例、平均成本、集中度）

步骤：
1. 初始化：第 0 日所有筹码成本 = close，总量 = 流通股本（或归一化为 1）
2. 逐日迭代：
   a. 换手率 = volume / 流通股本（如无股本数据，用成交量归一化）
   b. 当日新成交筹码：成本均匀分布在 [low, high]
   c. 旧筹码按 (1 - 换手率) 比例保留
   d. 新筹码按换手率比例加入
   e. 合并得到当日筹码分布 histogram
3. 计算：
   - 获利比例 = 成本 < close 的筹码占比
   - 平均成本 = 加权平均
   - 集中度 = (90%分位成本 - 10%分位成本) / 平均成本
```

**精度说明**：这是粗粒度估算，精度远低于分时数据，但用于回测统计足够。

### 3.3 技术指标（indicators.py）

计算以下指标（每只股票独立）：

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| MA5/10/20/60 | 滑动平均 | 趋势判断、支撑压力 |
| 乖离率(Bias) | (Close - MA) / MA | 超买超卖 |
| MACD | EMA12/26/9 | 趋势转折 |
| RSI(6/12/24) | 相对强弱 | 超买超卖 |
| 量比 | 当日成交量 / 前5日均量 | 量能异常 |
| 振幅 | (High - Low) / PreClose | 波动率 |
| 筹码分布 | chip_estimator 输出 | 成本结构 |

### 3.4 规则发现（rule_discovery.py）

从统计数据中发现规律，每条规则包含：
- `name`: 规则名称
- `condition`: 触发条件（函数）
- `sample_count`: 样本数
- `win_rate`: 胜率
- `avg_return`: 平均收益
- `confidence`: 置信度（统计显著性）

**规则类型**：

#### 3.4.1 均线支撑/压力规则

```python
def discover_ma_support_rule(
    df: pd.DataFrame,
    ma_period: int = 20,
    touch_threshold_pct: float = 0.5,  # 价格触及均线 ±0.5% 算触碰
    forward_days: int = 5,
) -> Rule:
    """
    统计：价格触及 MA20 后 forward_days 天的涨跌分布。
    返回：支撑率（上涨概率）、压力率（下跌概率）。
    """
```

#### 3.4.2 量价关系规则

```python
def discover_volume_price_rules(
    df: pd.DataFrame,
) -> List[Rule]:
    """
    发现以下规律：
    - 天量（量比 > 3）后 N 天走势分布
    - 地量（量比 < 0.5）后 N 天走势分布
    - 放量上涨 vs 缩量上涨的胜率差异
    - 量价背离（价涨量缩 / 价跌量增）后的走势
    """
```

#### 3.4.3 形态规则

```python
def discover_pattern_rules(
    df: pd.DataFrame,
) -> List[Rule]:
    """
    发现以下形态规律：
    - 多头排列（MA5>MA10>MA20）持续性
    - 金叉（MA5上穿MA10）后胜率
    - RSI 超卖反弹率
    - MACD 底背离胜率
    """
```

### 3.5 交易信号生成（signal_generator.py）

纯算法生成交易信号，**替代 LLM**。

```python
@dataclass
class AlgorithmSignal:
    date: date
    code: str
    action: str  # "buy" | "sell" | "hold" | "wait"
    entry_price: Optional[float]  # 建议入场价
    stop_loss: Optional[float]    # 建议止损
    take_profit: Optional[float]  # 建议止盈
    reasons: List[str]            # 触发理由（规则名称列表）
    confidence: float             # 综合置信度 0-1
```

**信号逻辑（可配置）**：

```
买入信号（buy）：
  条件1: MA5 > MA10 > MA20（多头排列）
  条件2: 乖离率 < 5%（不追高）
  条件3: 缩量回调 或 放量突破
  条件4: 筹码获利比例 30%-80%（健康区间）
  条件5: RSI 不在超买区（<70）
  → entry_price = MA5 或 MA10（回踩位）
  → stop_loss = MA20 或 入场价 - 3%
  → take_profit = 前高 或 入场价 + 6%

卖出信号（sell）：
  条件1: MA5 < MA10 < MA20（空头排列）
  条件2: 放量跌破 MA20
  条件3: RSI > 70 且乖离率 > 5%（超买）

持有（hold）：
  已持有多头仓位，趋势未破坏

观望（wait）：
  不满足以上任何条件
```

### 3.6 回测验证（backtest_runner.py）

复用 `BacktestEngine.evaluate_single()` 的验证逻辑，但输入从 LLM 建议改为算法信号。

```python
class TechnicalBacktestRunner:
    def run_single_stock(
        self,
        code: str,
        df: pd.DataFrame,
        signals: List[AlgorithmSignal],
        eval_window_days: int,
    ) -> List[EvaluationResult]:
        """对单只股票的每个信号，验证后续 eval_window_days 的准确性。"""

    def run_multi_stock(
        self,
        code_dfs: Dict[str, pd.DataFrame],
        eval_window_days: int,
    ) -> Dict[str, List[EvaluationResult]]:
        """多股并行回测。"""
```

### 3.7 跨股分析（cross_stock.py）

```python
def analyze_correlations(
    code_dfs: Dict[str, pd.DataFrame],
    lookback_days: int = 60,
) -> CrossStockAnalysis:
    """
    分析多股之间的关系：
    1. 皮尔逊相关系数矩阵（收盘价）
    2. 成交量相关系数矩阵
    3. 领先-滞后分析（Granger Causality 简化版）
    4. 共振检测：多股同日出现同向大幅波动的频率
    """
```

### 3.8 结果输出（output_writer.py）

输出到独立文件，不写入数据库。

```python
def write_results(
    output_path: str,
    meta: BacktestMeta,
    per_stock: Dict[str, PerStockResult],
    cross_stock: Optional[CrossStockAnalysis],
) -> str:
    """写入 JSON 文件，返回文件路径。"""
```

**输出 JSON 结构**：

```json
{
  "meta": {
    "mode": "historical",
    "codes": ["600519", "000858"],
    "date_range": ["2024-01-01", "2024-06-01"],
    "eval_window_days": 10,
    "generated_at": "2025-05-02T10:00:00",
    "version": "1.0"
  },
  "per_stock": {
    "600519": {
      "rules": [
        {
          "name": "MA20支撑",
          "condition": "价格触及MA20±0.5%",
          "sample_count": 23,
          "win_rate": 0.65,
          "avg_return_5d": 2.3,
          "confidence": 0.78
        }
      ],
      "signals": [
        {
          "date": "2024-03-15",
          "action": "buy",
          "entry_price": 1680.0,
          "stop_loss": 1620.0,
          "take_profit": 1780.0,
          "reasons": ["多头排列", "缩量回调"],
          "confidence": 0.82
        }
      ],
      "evaluations": [
        {
          "signal_date": "2024-03-15",
          "action": "buy",
          "outcome": "win",
          "stock_return_pct": 3.5,
          "hit_take_profit": true,
          "hit_stop_loss": false,
          "direction_correct": true
        }
      ],
      "summary": {
        "total_signals": 45,
        "win_rate": 0.58,
        "avg_return_pct": 1.8,
        "max_drawdown_pct": -5.2
      }
    }
  },
  "cross_stock": {
    "correlations": [
      {
        "code_a": "600519",
        "code_b": "000858",
        "price_correlation": 0.72,
        "volume_correlation": 0.45
      }
    ],
    "lead_lag": [
      {
        "leader": "600519",
        "follower": "000858",
        "lag_days": 1,
        "correlation": 0.68
      }
    ],
    "resonance": [
      {
        "date": "2024-04-10",
        "codes": ["600519", "000858"],
        "direction": "up",
        "magnitude": "large"
      }
    ]
  }
}
```

---

## 4. API 设计

### 4.1 新路由（独立文件）

```python
# api/routers/technical_backtest.py

from fastapi import APIRouter

router = APIRouter(prefix="/technical-backtest", tags=["technical-backtest"])

@router.post("/run")
async def run_technical_backtest(
    request: TechnicalBacktestRequest,
) -> TechnicalBacktestResponse:
    """
    运行纯算法技术面回测。

    模式切换由前端单选按钮控制：
    - /backtest/run (已有) → AI 预测验证模式
    - /technical-backtest/run (新增) → 纯算法历史回测模式
    """

@router.get("/results/{result_id}")
async def get_result(
    result_id: str,
) -> dict:
    """读取回测结果 JSON 文件。"""

@router.get("/results/{result_id}/download")
async def download_result(
    result_id: str,
) -> FileResponse:
    """下载回测结果文件。"""
```

### 4.2 请求模型

```python
class TechnicalBacktestRequest(BaseModel):
    codes: List[str]                      # 股票代码列表
    start_date: date                      # 回测开始日期
    end_date: date                        # 回测结束日期
    step_days: int = 1                    # 信号生成步长（默认每日）
    eval_window_days: int = 10            # 验证窗口天数
    max_days: Optional[int] = None        # 最大回测天数（限制）
    include_cross_stock: bool = True      # 是否进行跨股分析
    output_format: str = "json"           # 输出格式（json / csv）
```

---

## 5. 前端集成

### 5.1 模式切换

回测页面增加单选按钮：

```
回测模式：
( ) AI 预测验证      — 基于已有分析记录验证 AI 准确率
(*) 纯算法历史回测   — 基于历史 K 线运行算法规则发现
```

### 5.2 纯算法回测界面

```
股票代码：____________（多选，支持批量）
开始日期：[2024-01-01]
结束日期：[2024-06-01]
步长：[1] 天
验证窗口：[10] 天
[ ] 启用跨股共振分析
[运行回测]
```

### 5.3 结果展示

图形化展示内容：
1. **K线图 + 信号标注**：在 K 线上标注买入/卖出信号点
2. **规律面板**：列出发现的统计规律及胜率
3. **胜率曲线**：滚动窗口胜率变化
4. **跨股共振图**：多股价格走势叠加，标注共振点
5. **领先滞后图**：两只股票的滞后相关系数

---

## 6. 文件组织

### 6.1 代码文件

```
src/core/technical_backtest/
├── __init__.py              # 导出主要入口
├── models.py                # 数据模型（Rule, Signal, Evaluation 等）
├── data_loader.py           # 历史数据加载
├── chip_estimator.py        # 筹码分布估算
├── indicators.py            # 技术指标计算
├── rule_discovery.py        # 规则发现算法
├── signal_generator.py      # 算法信号生成
├── backtest_runner.py       # 回测执行
├── cross_stock.py           # 跨股分析
└── output_writer.py         # 结果输出

api/routers/
└── technical_backtest.py    # FastAPI 路由
```

### 6.2 输出文件

```
outputs/technical_backtest/
├── result_{timestamp}_{hash}.json   # 回测结果
└── index.json                        # 结果索引
```

---

## 7. 关键算法细节

### 7.1 筹码分布估算（简化版）

```python
def estimate_chip_distribution(
    df: pd.DataFrame,
    n_bins: int = 50,
) -> pd.DataFrame:
    """
    基于日 K 线估算筹码分布。

    假设：
    - 当日成交均匀分布在 [low, high] 区间
    - 换手率 = volume / float_share（如无知情，用相对换手率）
    - 旧筹码按 (1 - turnover) 比例保留
    - 新筹码成本均匀分布

    返回 DataFrame，每行包含：
    - profit_ratio: 获利比例
    - avg_cost: 平均成本
    - concentration_90: 90% 筹码集中度
    - concentration_70: 70% 筹码集中度
    """
```

### 7.2 信号置信度计算

```
confidence = Σ(rule_weight_i × rule_confidence_i) / Σ(rule_weight_i)

其中：
- rule_confidence = min(1.0, sample_count / 30) × win_rate
- rule_weight 根据规则类型预设（如均线规则权重 0.3，量价规则权重 0.2）
```

### 7.3 跨股领先滞后分析（简化 Granger）

```python
def lead_lag_analysis(
    price_a: pd.Series,
    price_b: pd.Series,
    max_lag: int = 5,
) -> Tuple[int, float]:
    """
    简化版领先滞后分析：
    1. 对 A 的收益率序列做滞后 0~max_lag 天
    2. 分别计算与 B 的收益率相关系数
    3. 取相关系数最大的滞后天数
    4. 若 lag > 0 且 correlation > 阈值，则 A 领先 B lag 天
    """
```

---

## 8. 性能考量

| 场景 | 预估耗时 | 优化策略 |
|------|----------|----------|
| 单股 1 年日 K 线 | <1s | 向量化计算 |
| 10 股 1 年日 K 线 | <5s | 多线程并行 |
| 100 股 3 年日 K 线 | <60s | 多进程 + 缓存指标 |
| 跨股相关性（10股） | <2s | 矩阵运算 |

---

## 9. 待确认事项

1. **筹码分布精度**：日成交量推断的粗粒度筹码分布是否可接受？
2. **信号规则权重**：买入/卖出条件的权重是否需要用户可配置？
3. **输出文件保留策略**：保留最近 N 个文件，还是永久保留？
4. **跨股分析范围**：用户选择的多股列表中自动分析全部两两组合，还是只分析指定组合？
5. **是否现在进入编码阶段？**

---

## 10. 实现顺序（编码阶段）

若确认设计，按以下顺序实现：

1. **Phase 1**：`models.py` + `chip_estimator.py` + `indicators.py`（基础工具）
2. **Phase 2**：`signal_generator.py` + `rule_discovery.py`（核心算法）
3. **Phase 3**：`backtest_runner.py` + `cross_stock.py`（回测引擎）
4. **Phase 4**：`output_writer.py` + `data_loader.py`（IO 层）
5. **Phase 5**：`api/routers/technical_backtest.py`（API 层）
6. **Phase 6**：前端集成（单选按钮 + 结果展示）

每 Phase 独立可测试，不触碰已有代码。
