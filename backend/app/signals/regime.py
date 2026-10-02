"""
推荐单引擎 — Regime Detector (v2)
基于特征的规则评分 + ADX 趋势识别 + Hurst 持续性 + 时间周期自适应。

设计要点（v2 改进，解决 v1「推荐单为空」问题）：
1. **降低 choppy bias**：choppy 不再是默认胜者；只在多空都不明显时才认领
2. **ADX 趋势识别**：ADX > 20 优先判定 bull/bear；ADX < 15 才允许 choppy
3. **Hurst 持续性**：Hurst > 0.55 表示趋势持续（H>0.5）；<0.45 表示均值回归
4. **时间周期自适应**：超短线（1m/5m/15m）choppy 阈值放宽；长线（1d）choppy 阈值收紧
5. **方向动能**：PDI vs NDI 不只是加分，而是强约束 bull/bear 方向

借鉴来源：
- RegimeSense (Apache-2.0): HMM 后验概率软分配 → 我们用规则打分 + softmax 近似
- MagicTradeBot (MIT): 多指标加权投票
- CryptoFrog (Apache-2.0): 多时间周期自适应
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from app.analytics.trend import adx


class Regime(Enum):
    """市场状态枚举"""
    BULL = "bull"
    BEAR = "bear"
    CHOPPY = "choppy"
    CRISIS = "crisis"


@dataclass(frozen=True, slots=True)
class RegimeInfo:
    regime: Regime
    confidence: float
    regime_probs: dict[Regime, float]
    description: str
    # 新增 v2 字段
    adx: float | None = None
    hurst: float | None = None
    trend_strength_label: str | None = None


# ─── 阈值定义（v2 — 时间周期自适应）───────────────────────────────────────────
# 同一逻辑对所有 timeframe 适用，但阈值按 timeframe 调整

# 累计 log return 阈值（按 timeframe 不同）
_RET_BULL_THRESHOLDS = {
    "1m": 0.001, "5m": 0.002, "15m": 0.005,
    "1h": 0.01, "4h": 0.02, "1d": 0.04,
}
_RET_BEAR_THRESHOLDS = {tf: -v for tf, v in _RET_BULL_THRESHOLDS.items()}

# realized_vol 阈值
_VOL_CHOPPY_MAX = {
    "1m": 0.003, "5m": 0.005, "15m": 0.007,
    "1h": 0.010, "4h": 0.015, "1d": 0.025,
}
_VOL_NORMAL_MAX = {
    "1m": 0.006, "5m": 0.010, "15m": 0.012,
    "1h": 0.020, "4h": 0.030, "1d": 0.050,
}
_VOL_CRISIS_THRESHOLD = {
    "1m": 0.015, "5m": 0.020, "15m": 0.025,
    "1h": 0.040, "4h": 0.060, "1d": 0.080,
}

# volume_ratio 异常放量
_VOLRATIO_HIGH = 1.5

# ADX 阈值（v2 新增）
_ADX_TRENDING = 20.0    # ADX >= 20 才认定为有趋势
_ADX_STRONG_TREND = 30.0  # ADX >= 30 强趋势

# Hurst 阈值（v2 新增）
_HURST_TRENDING = 0.55
_HURST_MEAN_REVERTING = 0.45


def _get_thresholds(timeframe: str) -> dict:
    """按 timeframe 返回阈值 dict（缺失 timeframe 退化到 1h）。"""
    return {
        "ret_bull": _RET_BULL_THRESHOLDS.get(timeframe, _RET_BULL_THRESHOLDS["1h"]),
        "ret_bear": _RET_BEAR_THRESHOLDS.get(timeframe, _RET_BEAR_THRESHOLDS["1h"]),
        "vol_choppy_max": _VOL_CHOPPY_MAX.get(timeframe, _VOL_CHOPPY_MAX["1h"]),
        "vol_normal_max": _VOL_NORMAL_MAX.get(timeframe, _VOL_NORMAL_MAX["1h"]),
        "vol_crisis": _VOL_CRISIS_THRESHOLD.get(timeframe, _VOL_CRISIS_THRESHOLD["1h"]),
    }


def _hurst_exponent(prices: np.ndarray, max_lag: int = 20) -> float:
    """
    计算 Hurst 指数（H）。H ∈ [0, 1]
      H > 0.5: 趋势持续（持久性）
      H = 0.5: 随机游走
      H < 0.5: 均值回归

    使用简化 R/S 法：log(R/S) ~ H * log(n)
    """
    if len(prices) < max_lag * 2:
        return 0.5  # 数据不足，返回中性

    # 转 log 价格
    log_prices = np.log(prices[prices > 0])
    if len(log_prices) < max_lag * 2:
        return 0.5

    lags = range(2, min(max_lag, len(log_prices) // 2))
    rs_values = []
    for lag in lags:
        # 把序列切成 lag 长度的段
        n_segments = len(log_prices) // lag
        if n_segments < 1:
            continue
        rs_segment_values = []
        for i in range(n_segments):
            segment = log_prices[i * lag : (i + 1) * lag]
            if len(segment) < 2:
                continue
            mean_adj = segment - segment.mean()
            cumulative = np.cumsum(mean_adj)
            r = cumulative.max() - cumulative.min()
            s = segment.std()
            if s > 0:
                rs_segment_values.append(r / s)
        if rs_segment_values:
            rs_values.append((lag, np.mean(rs_segment_values)))

    if len(rs_values) < 3:
        return 0.5

    lags_arr = np.array([x[0] for x in rs_values], dtype=np.float64)
    rs_arr = np.array([x[1] for x in rs_values], dtype=np.float64)
    # 过滤掉 0 值（无法取 log）
    valid = (rs_arr > 0) & (lags_arr > 0)
    if valid.sum() < 3:
        return 0.5

    log_lags = np.log(lags_arr[valid])
    log_rs = np.log(rs_arr[valid])

    # 简单线性回归
    slope, _ = np.polyfit(log_lags, log_rs, 1)
    return float(np.clip(slope, 0.0, 1.0))


class RegimeDetector:
    """
    基于规则的 Regime 检测器（4 状态 soft assignment, v2）。

    v2 评分逻辑：
      - CRISIS: 极端波动 + 异常放量（最优先）
      - BULL:   ADX>=20 & +DI>-DI & 正收益 → 强约束
      - BEAR:   ADX>=20 & -DI>+DI & 负收益 → 强约束
      - CHOPPY: ADX<15 OR 持续性低（Hurst<0.45）→ 弱约束（v1 过度宽松）

    时间周期自适应：超短线（1m/5m/15m）波动天然小，choppy 阈值放宽；
    长线（1d）波动天然大，bull/bear 阈值放宽。
    """

    N_REGIMES = 4

    def __init__(self, timeframe: str = "1h") -> None:
        self._timeframe = timeframe
        self._state_probs: np.ndarray | None = None
        self._hidden_state: int = 0  # 默认 bull（v2: 不再默认 choppy）
        self._adx_val: float | None = None
        self._hurst_val: float | None = None

    @staticmethod
    def compute_features(
        returns: np.ndarray,
        volumes: np.ndarray,
    ) -> np.ndarray:
        """
        从收益率和成交量序列计算特征矩阵 (n_samples, 3)。

        列 0: log_return
        列 1: realized_vol (20-period rolling std)
        列 2: volume_ratio (成交量 / 20日均量)
        """
        n = len(returns)
        features = np.zeros((n, 3), dtype=np.float64)
        features[:, 0] = returns

        if n >= 20:
            roll_std = np.array([
                np.std(returns[max(0, i - 19):i + 1])
                for i in range(n)
            ], dtype=np.float64)
            features[:, 1] = roll_std
        else:
            features[:, 1] = np.full(n, np.std(returns) if n > 0 else 0)

        if len(volumes) >= 20:
            vol_ma20 = np.convolve(volumes, np.ones(20) / 20, mode="same")
            vol_ma20 = np.where(vol_ma20 == 0, 1, vol_ma20)
            features[:, 2] = volumes / vol_ma20
        else:
            features[:, 2] = 1.0

        return features

    @staticmethod
    def _score_regimes(
        features: np.ndarray,
        timeframe: str,
        adx_val: float | None = None,
        pdi_val: float | None = None,
        ndi_val: float | None = None,
        hurst_val: float | None = None,
    ) -> tuple[np.ndarray, float, float]:
        """
        给定 (n_samples, 3) 特征矩阵，返回 (4,) 状态概率分布 + (adx, hurst)。

        v2 关键改进：
        - CHOPPY 不再是默认赢家；只在多空都不明显时才加分
        - ADX > 20 + PDI/NDI 一致 → 强 bull/bear 加分
        - Hurst > 0.55 → 趋势加分（持久性）
        - 时间周期自适应阈值
        """
        recent = features[-30:] if len(features) >= 30 else features

        mean_ret = float(np.mean(recent[:, 0]))
        mean_vol = float(np.mean(recent[:, 1]))
        mean_vr = float(np.mean(recent[:, 2]))
        max_vol = float(np.max(recent[:, 1]))
        max_vr = float(np.max(recent[:, 2]))
        cum_ret = float(np.sum(recent[:, 0]))

        thr = _get_thresholds(timeframe)
        ret_bull_thr = thr["ret_bull"]
        ret_bear_thr = thr["ret_bear"]
        vol_choppy_max = thr["vol_choppy_max"]
        vol_normal_max = thr["vol_normal_max"]
        vol_crisis_thr = thr["vol_crisis"]

        # ── 评分 ──────────────────────────────────────────────────
        bull_score = 0.0
        bear_score = 0.0
        choppy_score = 0.0
        crisis_score = 0.0

        # CRISIS：极端波动 + 异常放量（最高优先级）
        if max_vol > vol_crisis_thr:
            crisis_score += 0.7
        if max_vr > _VOLRATIO_HIGH:
            crisis_score += 0.3
        if mean_vol > vol_normal_max * 1.5:  # v2: 比 normal 更高才加分
            crisis_score += 0.3

        # ── v2: ADX 趋势识别作为 bull/bear 的强约束 ────────────────
        has_clear_trend = (
            adx_val is not None
            and adx_val >= _ADX_TRENDING
            and pdi_val is not None
            and ndi_val is not None
        )
        trend_is_bull = has_clear_trend and pdi_val > ndi_val  # type: ignore[operator]
        trend_is_bear = has_clear_trend and ndi_val > pdi_val  # type: ignore[operator]
        strong_trend = adx_val is not None and adx_val >= _ADX_STRONG_TREND

        # BULL：正收益 + ADX 多头趋势
        if cum_ret > ret_bull_thr:
            bull_score += 0.5
        elif cum_ret > ret_bull_thr / 2:
            bull_score += 0.25

        if trend_is_bull:
            # v2: ADX 多头趋势是 bull 的强信号
            bull_score += 0.4
            if strong_trend:
                bull_score += 0.2  # 强趋势额外加分

        if mean_vol < vol_normal_max:
            bull_score += 0.15  # v2: 弱化（v1 是 0.2）
        if mean_vr > 1.0 and mean_vr < _VOLRATIO_HIGH:
            bull_score += 0.2  # v2: 健康放量

        # v2: Hurst 持续性加分
        if hurst_val is not None and hurst_val > _HURST_TRENDING:
            bull_score += 0.15

        # BEAR：负收益 + ADX 空头趋势
        if cum_ret < ret_bear_thr:
            bear_score += 0.5
        elif cum_ret < ret_bear_thr / 2:
            bear_score += 0.25

        if trend_is_bear:
            bear_score += 0.4
            if strong_trend:
                bear_score += 0.2

        if mean_vol < vol_normal_max:
            bear_score += 0.15
        if mean_vr > 1.0:
            bear_score += 0.15

        if hurst_val is not None and hurst_val > _HURST_TRENDING:
            bear_score += 0.15

        # CHOPPY：v2 大幅收紧条件
        # 仅当 ADX<15（无趋势）+ Hurst<0.5（无持续性）+ 累计收益小 + 波动小 才算 choppy
        adx_low = adx_val is None or adx_val < 15
        hurst_low = hurst_val is None or hurst_val < _HURST_MEAN_REVERTING

        if abs(cum_ret) < ret_bull_thr:  # 累计收益小
            choppy_score += 0.2  # v2: 从 0.4 降到 0.2
        if mean_vol < vol_choppy_max:
            choppy_score += 0.2  # v2: 从 0.4 降到 0.2
        if max_vol < vol_normal_max:
            choppy_score += 0.1  # v2: 从 0.2 降到 0.1

        # v2: ADX/Hurst 都不支持趋势时，choppy 额外加分
        if adx_low and hurst_low:
            choppy_score += 0.3

        # ── v2 互斥规则（更精细） ────────────────────────────────
        if crisis_score > 0.5:
            # crisis 出现时，压制所有其他状态
            bull_score *= 0.3
            bear_score *= 0.3
            choppy_score *= 0.2

        # 强 ADX 趋势时，强烈压制 choppy（v2 新规则）
        if strong_trend:
            choppy_score *= 0.3
        elif has_clear_trend:
            choppy_score *= 0.5

        # 强累计收益趋势时，choppy 抑制
        if abs(cum_ret) > ret_bull_thr * 2:
            choppy_score *= 0.4

        # Softmax 归一化（温度 1.0）
        scores = np.array(
            [bull_score, bear_score, choppy_score, crisis_score],
            dtype=np.float64,
        )
        scores = np.clip(scores, 0.0, None) + 0.05  # 平滑 floor
        exp = np.exp(scores - scores.max())
        probs = exp / exp.sum()
        return probs, (adx_val or 0.0), (hurst_val or 0.5)

    def update(
        self,
        returns: np.ndarray,
        volumes: np.ndarray,
        high: np.ndarray | None = None,
        low: np.ndarray | None = None,
        close: np.ndarray | None = None,
    ) -> RegimeInfo:
        """用最新 K 线数据更新状态估计（v2: 可选传入 high/low/close 计算 ADX/Hurst）。"""
        features = self.compute_features(returns, volumes)

        # v2: 计算 ADX（如果有 high/low/close）
        adx_val = pdi_val = ndi_val = None
        if high is not None and low is not None and close is not None and len(close) >= 28:
            try:
                adx_arr, pdi_arr, ndi_arr = adx(high, low, close, 14)
                if not np.isnan(adx_arr[-1]):
                    adx_val = float(adx_arr[-1])
                    pdi_val = float(pdi_arr[-1])
                    ndi_val = float(ndi_arr[-1])
                    self._adx_val = adx_val
            except Exception:
                pass

        # v2: 计算 Hurst（持久性）
        hurst_val = None
        if close is not None and len(close) >= 60:
            try:
                hurst_val = _hurst_exponent(close, max_lag=20)
                self._hurst_val = hurst_val
            except Exception:
                pass

        self._state_probs, adx_now, hurst_now = self._score_regimes(
            features,
            self._timeframe,
            adx_val=adx_val,
            pdi_val=pdi_val,
            ndi_val=ndi_val,
            hurst_val=hurst_val,
        )
        self._hidden_state = int(np.argmax(self._state_probs))

        regime_map = [Regime.BULL, Regime.BEAR, Regime.CHOPPY, Regime.CRISIS]
        regime = regime_map[self._hidden_state]
        descriptions = {
            Regime.BULL: "上涨趋势·顺势做多",
            Regime.BEAR: "下跌趋势·谨慎做空",
            Regime.CHOPPY: "震荡区间·高抛低吸",
            Regime.CRISIS: "极端波动·观望为主",
        }

        # trend_strength label
        if adx_val is None:
            trend_label = "ADX数据不足"
        elif adx_val < 15:
            trend_label = "无趋势"
        elif adx_val < 25:
            trend_label = "弱趋势"
        elif adx_val < 50:
            trend_label = "中等趋势"
        else:
            trend_label = "强趋势"

        return RegimeInfo(
            regime=regime,
            confidence=float(self._state_probs[self._hidden_state]),
            regime_probs={
                regime_map[i]: float(self._state_probs[i])
                for i in range(self.N_REGIMES)
            },
            description=descriptions[regime],
            adx=adx_val,
            hurst=hurst_val,
            trend_strength_label=trend_label,
        )

    def get_current(self) -> RegimeInfo:
        """返回当前状态（需先调用 update）。"""
        if self._state_probs is None:
            return RegimeInfo(
                regime=Regime.CHOPPY,
                confidence=0.3,
                regime_probs={r: 0.25 for r in Regime},
                description="未初始化·默认震荡",
                adx=None,
                hurst=None,
                trend_strength_label="未初始化",
            )
        regime_map = [Regime.BULL, Regime.BEAR, Regime.CHOPPY, Regime.CRISIS]
        regime = regime_map[self._hidden_state]
        descriptions = {
            Regime.BULL: "上涨趋势·顺势做多",
            Regime.BEAR: "下跌趋势·谨慎做空",
            Regime.CHOPPY: "震荡区间·高抛低吸",
            Regime.CRISIS: "极端波动·观望为主",
        }

        adx_now = self._adx_val
        trend_label = None
        if adx_now is not None:
            if adx_now < 15:
                trend_label = "无趋势"
            elif adx_now < 25:
                trend_label = "弱趋势"
            elif adx_now < 50:
                trend_label = "中等趋势"
            else:
                trend_label = "强趋势"

        return RegimeInfo(
            regime=regime,
            confidence=float(self._state_probs[self._hidden_state]),
            regime_probs={
                regime_map[i]: float(self._state_probs[i])
                for i in range(self.N_REGIMES)
            },
            description=descriptions[regime],
            adx=adx_now,
            hurst=self._hurst_val,
            trend_strength_label=trend_label,
        )
