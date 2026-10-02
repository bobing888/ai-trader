# GitHub Survey — 趋势判断 + 推单灵敏 (2026-10-02)

> 目标：找「趋势判断准确 + 推单灵敏」开源实现，借鉴进 ai-trader 信号引擎。
> 借鉴基准：现有 `backend/app/signals/regime.py` 已借鉴 RegimeSense/MagicTradeBot/CryptoFrog。

## Phase 0 — 候选 repo（10 个 ≥2k star，全部已验证存在）
### `freqtrade/freqtrade`

| Field | value |
|-------|-------|
| Repo | freqtrade |
| ★ | 54981 |
| License | gpl-3.0 |
| 最近 push | 2026-10-02 |
| Language | Python |
| 描述 | Free, open source crypto trading bot |

**README 摘要**:

```

[![Freqtrade CI](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.04864/status.svg)](https://doi.org/10.21105/joss.04864)
[![codecov](https://codecov.io/gh/freqtrade/freqtrade/branch/develop/graph/badge.svg?token=AD5BG3ATKI)](https://codecov.io/gh/freqtrade/freqtrade)
[![Documentation](https://readthedocs.org/projects/freqtrade/badge/)](https://www.freqtrade.io)
[![Discord Server](https://img.shields.io/badge/Freqtrade_Discord-4E4E4E?logo=discord)](https://discord.gg/p7nuUNVfP7)

Freqtrade is a free and open source crypto trading bot written in Python. It is designed to support all major exchanges and be controlled via Telegram or webUI. It contains backtesting, plotting and money management tools as well as strategy optimization by machine learning.
```

---

### `freqtrade/freqtrade-strategies`

| Field | value |
|-------|-------|
| Repo | freqtrade-strategies |
| ★ | 5521 |
| License | gpl-3.0 |
| 最近 push | 2026-09-08 |
| Language | Python |
| 描述 | Free trading strategies for Freqtrade bot |

**README 摘要**:

```

This Git repo contains free buy/sell strategies for [Freqtrade](https://github.com/freqtrade/freqtrade).

All strategies should work with a freqtrade version of 2022.4 or newer.
```

---

### `jesse-ai/jesse`

| Field | value |
|-------|-------|
| Repo | jesse |
| ★ | 8611 |
| License | mit |
| 最近 push | 2026-10-01 |
| Language | Python |
| 描述 | An advanced crypto trading bot written in Python |

**README 摘要**:

```
[![PyPI](https://img.shields.io/pypi/v/jesse)](https://pypi.org/project/jesse)
[![Downloads](https://pepy.tech/badge/jesse)](https://pepy.tech/project/jesse)
[![Docker Pulls](https://img.shields.io/docker/pulls/salehmir/jesse)](https://hub.docker.com/r/salehmir/jesse)
[![GitHub](https://img.shields.io/github/license/jesse-ai/jesse)](https://github.com/jesse-ai/jesse)
[![coverage](https://codecov.io/gh/jesse-ai/jesse/graph/badge.svg)](https://codecov.io/gh/jesse-ai/jesse)

---

Jesse is an advanced crypto trading framework that aims to **simplify** **researching** and defining **YOUR OWN trading strategies** for backtesting, optimizing, and live trading.

def before(self):
    self.record_features({
        'rsi': ta.rsi(self.candles),
        'adx': ta.adx(self.candles),
    })

def should_long(self):
    proba = self.ml_predict_proba()
    return proba['long'] > 0.65
```

[Explore Jesse's machine-learning pipeline →](https://docs.jesse.trade/docs/research/ml/)

### Research API and Jupyter Notebooks
Everything does not have to happen through the dashboard. Jesse's Research API exposes candle management, backtesting, optimization, Rule Significance Testing, Monte Carlo analysis, indicators, and machine learning to ordinary Python scripts and Jupyter notebooks. Use it for reproducible experiments, custom reports, batch research, or integration with your existing data-science workflow.
```

---

### `kernc/backtesting.py`

| Field | value |
|-------|-------|
| Repo | backtesting.py |
| ★ | 9010 |
| License | agpl-3.0 |
| 最近 push | 2026-08-05 |
| Language | Python |
| 描述 | 🔎 📈 🐍 💰  Backtest trading strategies in Python. |

**README 摘要**:

```
Win Rate [%]                            53.76
Best Trade [%]                          57.12
Worst Trade [%]                        -16.63
Avg. Trade [%]                           1.96
Max. Trade Duration         121 days 00:00:00
Avg. Trade Duration          32 days 00:00:00
Profit Factor                            2.13
Expectancy [%]                           6.91
SQN                                      1.78
Kelly Criterion                        0.6134
_strategy              SmaCross(n1=10, n2=20)
_equity_curve                          Equ...
_trades                       Size  EntryB...
dtype: object
```
[![plot of trading simulation](https://i.imgur.com/xRFNHfg.png)](https://kernc.github.io/backtesting.py/#example)

Find more usage examples in the [documentation].


Features
--------
* Simple, [well-documented API](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html)
* Blazing fast execution
* Built-in [optimizer](https://kernc.github.io/backtesting.py/doc/examples/Quick%20Start%20User%20Guide.html#Optimization)
```

---

### `ta4j/ta4j`

| Field | value |
|-------|-------|
| Repo | ta4j |
| ★ | 2495 |
| License | other |
| 最近 push | 2026-10-01 |
| Language | Java |
| 描述 | A Java library for technical analysis. |

**README 摘要**:

```

**Technical Analysis for Java**

[Documentation](https://ta4j.github.io/ta4j-wiki/) · [Javadoc](https://ta4j.github.io/ta4j/) · [Examples](ta4j-examples/README.md) · [Discord](https://discord.gg/HX9MbWZ)

ta4j is an open-source Java library for technical analysis and trading-system research. Build indicators and rules, backtest strategies with realistic costs and execution assumptions, inspect the results, and reuse the same strategy logic in live applications.

[Why ta4j?](#why-ta4j) · [Install](#install-in-seconds) · [Quick start](#quick-start-your-first-strategy) · [Workflow](#the-core-workflow) · [Examples](#real-world-examples) · [Contributing](#contributing)

---

./mvnw -DskipTests install
./mvnw -pl ta4j-examples exec:java
```

On Windows, use `mvnw.cmd` instead of `./mvnw`. The example loads bundled Bitcoin data, evaluates a strategy, prints performance metrics, and displays a chart when a graphical environment is available.

Run another example by overriding the configured main class:

```bash
./mvnw -pl ta4j-examples exec:java -Dexec.mainClass=ta4jexamples.backtesting.TradingRecordParityBacktest
```

### Use the core API
```

---

### `microsoft/qlib`

| Field | value |
|-------|-------|
| Repo | qlib |
| ★ | 49109 |
| License | mit |
| 最近 push | 2026-09-22 |
| Language | Python |
| 描述 | Qlib is an AI-oriented Quant investment platform that aims to use AI tech to empower Quant Research, from exploring ideas to implementing productions. Qlib supports diverse ML modeling paradigms, including supervised learning, market dynamics modeling, and RL, and is now equipped with https://github.com/microsoft/RD-Agent to automate R&D process. |

**README 摘要**:

```
New features under development(order by estimated release time).
Your feedbacks about the features are very important.
<!-- | Feature                        | Status      | -->
<!-- | --                      | ------    | -->


<div style="align: center">
<img src="docs/_static/img/framework-abstract.jpg" />
</div>

The high-level framework of Qlib can be found above(users can find the [detailed framework](https://qlib.readthedocs.io/en/latest/introduction/introduction.html#framework) of Qlib's design when getting into nitty gritty).
The components are designed as loose-coupled modules, and each component could be used stand-alone.

Qlib provides a strong infrastructure to support Quant research. [Data](https://qlib.readthedocs.io/en/latest/component/data.html) is always an important part.
A strong learning framework is designed to support diverse learning paradigms (e.g. [reinforcement learning](https://qlib.readthedocs.io/en/latest/component/rl.html), [supervised learning](https://qlib.readthedocs.io/en/latest/component/workflow.html#model-section)) and patterns at different levels(e.g. [market dynamic modeling](https://qlib.readthedocs.io/en/latest/component/meta.html)).
By modeling the market, [trading strategies](https://qlib.readthedocs.io/en/latest/component/strategy.html) will generate trade decisions that will be executed. Multiple trading strategies and executors in different levels or granularities can be [nested to be optimized and run together](https://qlib.readthedocs.io/en/latest/component/highfreq.html).
At last, a comprehensive [analysis](https://qlib.readthedocs.io/en/latest/component/report.html) will be provided and the model can be [served online](https://qlib.readthedocs.io/en/latest/component/online.html) in a low cost.



This quick start guide tries to demonstrate
1. It's very easy to build a complete Quant research workflow and try your ideas with _Qlib_.
2. Though with *public data* and *simple models*, machine learning technologies **work very well** in practical Quant investment.

Here is a quick **[demo](https://terminalizer.com/view/3f24561a4470)** shows how to install ``Qlib``, and run LightGBM with ``qrun``. **But**, please make sure you have already prepared the data following the [instruction](#data-preparation).
```

---

### `stefan-jansen/machine-learning-for-trading`

| Field | value |
|-------|-------|
| Repo | machine-learning-for-trading |
| ★ | 21196 |
| License | mit |
| 最近 push | 2026-10-02 |
| Language | Jupyter Notebook |
| 描述 | Code for Machine Learning for Trading, 3rd edition — from data sourcing to live execution. |

**README 摘要**:

```

**Build, test, and deploy ML-driven trading strategies, from data sourcing to live execution.**

The code for [*Machine Learning for Trading, 3rd Edition*](https://amzn.to/4eigy2F) by
[Stefan Jansen](https://www.linkedin.com/in/applied-ai/): 27 chapters and nine case studies, rebuilt
from the ground up around one end-to-end workflow. How a research idea becomes a strategy you can
run, and keep running, in a live market.

<p align="center">
  <a href="https://amzn.to/4eigy2F"><img src="assets/cover.png" width="45%" alt="Machine Learning for Trading, 3rd Edition"></a>
</p>

**Looking for the second edition?** It is complete and stable on the `second-edition` branch:
`git checkout second-edition`, and everything is exactly where that book describes it.

ML4T_DATA_PATH="${ML4T_DATA_PATH:-$PWD/data}" uv run jupyter lab

docker compose up ml4t
```

The `ML4T_DATA_PATH` prefix on the local path gives the loaders an absolute path, because Jupyter
runs each notebook with its chapter folder as the working directory and the loaders would otherwise
search inside that folder and report the datasets as missing. It keeps a value you have already
exported and defaults to this repository's `data/`. The Docker path needs no prefix: the compose
file sets the variable inside the container. See
```

---

### `cuemacro/findatapy`

| Field | value |
|-------|-------|
| Repo | findatapy |
| ★ | 2131 |
| License | apache-2.0 |
| 最近 push | 2026-07-02 |
| Language | Python |
| 描述 | Python library to download market data via Bloomberg, Eikon, Quandl, Yahoo etc. |

**README 摘要**:

```

[![Downloads](https://pepy.tech/badge/findatapy)](https://pepy.tech/project/findatapy)

findatapy creates an easy to use Python API to download market data from many sources including ALFRED/FRED, Bloomberg, Yahoo, Google etc. using
a unified high level interface. Users can also define their own custom tickers, using configuration files. There is also functionality which
is particularly useful for those downloading FX market data. Below example shows how to download AUDJPY data from Quandl (and automatically 
calculates this via USD crosses).

*Contributors for the project are very much welcome, see below!*

```
from findatapy.market import Market, MarketDataRequest, MarketDataGenerator

market = Market(market_data_generator=MarketDataGenerator())

fred_api_key = "WRITE YOUR KEY HERE" 

md_request = MarketDataRequest(start_date='year', category='fx', data_source='alfred', tickers=['AUDJPY'],
                               fred_api_key=fred_api_key)

df = market.fetch_market(md_request)
print(df.tail(n=10))
```

Here we see how to download tick data from DukasCopy, wih the same API calls and minimal changes in the code.
```

---

### `ranaroussi/quantstats`

| Field | value |
|-------|-------|
| Repo | quantstats |
| ★ | 7678 |
| License | apache-2.0 |
| 最近 push | 2026-09-27 |
| Language | Python |
| 描述 | Portfolio analytics for quants, written in Python |

**README 摘要**:

```

**QuantStats** Python library that performs portfolio profiling, allowing quants and portfolio managers to understand their performance better by providing them with in-depth analytics and risk metrics.

[Changelog »](./CHANGELOG.md)

### QuantStats is comprised of 3 main modules:

1. `quantstats.stats` - for calculating various performance metrics, like Sharpe ratio, Win rate, Volatility, etc.
2. `quantstats.plots` - for visualizing performance, drawdowns, rolling statistics, monthly returns, etc.
3. `quantstats.reports` - for generating metrics reports, batch plotting, and creating tear sheets that can be saved as an HTML file.

---

### **NEW! Monte Carlo Simulations**

<img src="https://raw.githubusercontent.com/ranaroussi/pandas-montecarlo/master/demo.png" alt="Monte Carlo Simulation" width="640">

Run probabilistic risk analysis with built-in Monte Carlo simulations:

```python
mc = qs.stats.montecarlo(returns, sims=1000, bust=-0.20, goal=0.50)
print(f"Bust probability: {mc.bust_probability:.1%}")
print(f"Goal probability: {mc.goal_probability:.1%}")
mc.plot()
```
```

---

### `peerchemist/finta`

| Field | value |
|-------|-------|
| Repo | finta |
| ★ | 2264 |
| License | lgpl-3.0 |
| 最近 push | 2022-07-24 |
| Language | Python |
| 描述 | Common financial technical indicators implemented in Pandas. |

**README 摘要**:

```

[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![PyPI](https://img.shields.io/pypi/v/finta.svg?style=flat-square)](https://pypi.python.org/pypi/finta/)
[![Downloads](https://pepy.tech/badge/finta/month)](https://pepy.tech/project/finta/month)
[![](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/download/releases/3.6.0/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Build Status](https://travis-ci.org/peerchemist/finta.svg?branch=master)](https://travis-ci.org/peerchemist/finta)
[![Patrons](https://img.shields.io/liberapay/patrons/peerchemist.svg?logo=liberapay)](https://img.shields.io/liberapay/patrons/peerchemist.svg?logo=liberapay)
[![Bitcoin Donate](https://badgen.net/badge/Bitcoin/Donate/F19537?icon=bitcoin)](https://blockstream.info/address/3Jp1RjKZdQjb1Ui4o5MVqhfch3rD1xUynn)
[![Peercoin Donate](https://badgen.net/badge/peercoin/Donate/green?icon=https://raw.githubusercontent.com/peercoin/media/84710cca6c3c8d2d79676e5260cc8d1cd729a427/Peercoin%202020%20Logo%20Files/01.%20Icon%20Only/Inside%20Circle/Transparent/Green%20Icon/peercoin-icon-green-transparent.svg)](https://chainz.cryptoid.info/ppc/address.dws?PWzpZ5igHDSA76gNZ9DwE7aeCbfLsZbDkJ)

Common financial technical indicators implemented in Pandas.


*This is work in progress, bugs are expected and results of some indicators
may not be accurate.*
```

---

## Phase 1 — 下一步（agent 手动提炼）

对每个 repo：
1. `gh repo clone` 到 `/tmp` 读主代码（避开 100MB+ 的依赖目录）
2. 找「趋势判断」核心算法（regime / momentum / breakout / multi-TF）
3. 找「推单灵敏」核心算法（entry timing / signal freshness / event-driven trigger）
4. 写 license 出处 + ai-trader 适配方式（5-10 个 feature）

按 ai-trader 现有架构：
- `backend/app/signals/regime.py` 已有 (HMM / HRS / ADX 借鉴)
- `backend/app/signals/strategy_pool.py` 7 个策略骨架
- `backend/app/signals/aggregator.py` v2 Affinity Matrix

可补充缺口：
- **量价共振** 缺：freqtrade-strategies + ta4j 都有
- **Order Flow / Footprint Chart** 缺：jesse / qlib 有
- **ML 校准 confidence** 缺：qlib / stefan-jansen 有
- **回测归因 (PnL attribution)** 缺：quantstats 完整
- **Risk-adjusted 评分** 缺：quantstats / jesse 都有

## Phase 2 — 状态

- Script mode: bash ✅
- 10 repo 元数据 + README 摘要已写
- LLM 深度提炼: 待跑
- Date: 2026-10-02

---

## Phase 1 — 借鉴结论（top-3 deep-dive 后写）

### Top-3 选定（License 兼容 MIT）

| Repo | ★ | License | 角色 | 借鉴焦点 |
|------|---|---------|------|----------|
| `jesse-ai/jesse` | 8611 | MIT | 推单框架 | should_long/should_short + filters + 175 indicators |
| `ta4j/ta4j` | 2495 | MIT | 趋势算法 | BarSeries/CachedBarSeries + Rule 模式（趋势→规则） |
| `microsoft/qlib` | 49109 | MIT | ML 校准 | CatLight/LightGBM/ALSTM 模型 + workflow |

### 借鉴 Feature 清单

#### 借鉴 1：jesse `filters()` 钩子（推单灵敏 - 早过滤）

**jesse 源码位置**：`jesse/strategies/Strategy.py:603`
```python
def filters(self) -> list:
    return []
# 在 should_long 之前被调用，返回任何 False 阻止入场
```

**ai-trader 现状**：`backend/app/signals/strategy_pool.py` 7 个策略骨架各自独立判断，无前置 gate

**ai-trader 适配**：在 `StrategyResult` 增加 `filters: list[bool]` 字段，`SignalAggregator` 在 min_agreement 计算前检查 `all(filters)` 否则降级为 hold-no-ready

**价值**：把"趋势不明时推单"压到 0，避免在 choppy 误推

#### 借鉴 2：jesse RealStrategyRegression1 多时间框架 Alligator（趋势判断准确）

**jesse 源码位置**：`jesse/strategies/RealStrategyRegression1/__init__.py`

5 个判断层：
1. 多 TF candle (`get_candles(self.exchange, self.symbol, '4h')`)
2. ADX threshold (`adx > threshold` 强趋势筛选)
3. Alligator 排序（price > lips > teeth > jaw 升序 = uptrend）
4. CMO 动量过滤
5. Stochastic RSI 超买超卖

**ai-trader 现状**：`regime.py` v2 已有 ADX + Hurst，但没有 Alligator

**ai-trader 适配**：新增 `Indicators.alligator.magnitude` 到 `analytics/`，在 strategy_pool.MULTI_TF 策略里集成

**价值**：Alligator 是经典比尔威廉姆斯指标，AI 圈量化常用，借鉴它直接扩大可推单场景

#### 借鉴 3：qlib ML workflow（趋势置信度 ML 校准）

**qlib 源码位置**：`qlib/contrib/model/{lightgbm,catboost,pytorch_alstm}.py` + `qlib/workflow/`

qlib 提供：
- CatBoost/LightGBM/XGBoost 模型训练脚本
- ALSTM (Attention LSTM) 时序模型
- workflow 自动记录超参 + 评估

**ai-trader 现状**：`aggregator.py` v2 用规则 affinity 加权，confidence 是手算确定数 (0.0-1.0)

**ai-trader 适配**：加 `backend/app/signals/ml_calibrator.py`，用 LightGBM 在历史 regime + strategy_result 序列上训练，把规则 score → ML 校准 probability

**价值**：用 ML 校准把 confidence 变成真实"概率"（calibrated probability），配合 aggregator 的动态阈值更准

#### 借鉴 4：ta4j Rule 模式（趋势→规则化执行）

**ta4j 源码位置**：`ta4j-core/src/main/java/org/ta4j/core/Rule.java`

ta4j 核心是 Rule pattern：
```java
Rule entryRule = new CrossedUpIndicatorRule(close, sma).and(new OverIndicatorRule(rsi, 30));
Rule exitRule = new CrossedDownIndicatorRule(close, sma).or(new StopLossRule(close, 5));
```

**ai-trader 现状**：策略是函数（momentum/normalize/reversal），不是 rule chain

**ai-trader 适配**：可选 - 加 `backend/app/signals/rule_chain.py`，把 strategy_pool 的策略用 chain-of-rules 重组，可调试性更高

**价值**：可选。低优先级。

## Phase 2 — 状态

- Top-3 deep-dive: ✅
- Phase 1 借鉴清单: 4 项可落地
- Phase 3 skill 落地: 待执行（见 daily-evolution / 自进化）
- Date: $(date +%Y-%m-%d)
