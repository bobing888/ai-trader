"""
推荐单引擎 — Regime Detector
基于特征的规则评分 (rule-based scoring) 检测市场状态。

保留 HMM 接口但用更稳定的实现：直接基于特征分布做 4-state soft assignment。
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np


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


# ─── 阈值定义（可调节）────────────────────────────────────────────────────────
# 基于经验 / 历史回测：特征值落在哪个区间 → 哪个 regime 权重更高

# log_return 累积值：20-period 累计 log return
_RET_BULL_THRESHOLD = 0.02   # > +2% → bull 倾向
_RET_BEAR_THRESHOLD = -0.02  # < -2% → bear 倾向

# realized_vol（未年化的 20-period rolling std）：crypto 1h 通常 0.005-0.05
_VOL_CHOPPY_MAX = 0.008
_VOL_NORMAL_MAX = 0.015
_VOL_CRISIS_THRESHOLD = 0.03

# volume_ratio: > 1.5 视为异常放量
_VOLRATIO_HIGH = 1.5


class RegimeDetector:
    """
    基于规则的 Regime 检测器（4 状态 soft assignment）。

    评分逻辑（每个状态给一个分数 0-1，然后 softmax）：
      - BULL:    high return + moderate vol + volume expansion
      - BEAR:    low return + moderate vol
      - CHOPPY:  near-zero return + low vol + no volume expansion
      - CRISIS:  any direction + very high vol + heavy volume expansion
    """

    N_REGIMES = 4

    def __init__(self) -> None:
        self._state_probs: np.ndarray | None = None
        self._hidden_state: int = 2  # 默认 choppy

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
                np.std(returns[max(0, i-19):i+1])
                for i in range(n)
            ], dtype=np.float64)
            features[:, 1] = roll_std
        else:
            features[:, 1] = np.full(n, np.std(returns) if n > 0 else 0)

        if len(volumes) >= 20:
            vol_ma20 = np.convolve(volumes, np.ones(20)/20, mode="same")
            vol_ma20 = np.where(vol_ma20 == 0, 1, vol_ma20)
            features[:, 2] = volumes / vol_ma20
        else:
            features[:, 2] = 1.0

        return features

    @staticmethod
    def _score_regimes(features: np.ndarray) -> np.ndarray:
        """
        给定 (n_samples, 3) 特征矩阵，返回 (4,) 状态概率分布。
        使用最近 30 个特征点（更近期权重更高）。
        """
        recent = features[-30:] if len(features) >= 30 else features

        # 综合特征：mean return, mean vol, mean vol_ratio, max vol, max vol_ratio
        mean_ret = float(np.mean(recent[:, 0]))
        mean_vol = float(np.mean(recent[:, 1]))
        mean_vr = float(np.mean(recent[:, 2]))
        max_vol = float(np.max(recent[:, 1]))
        max_vr = float(np.max(recent[:, 2]))

        # 累计 log return（过去 30 根 K 线）
        cum_ret = float(np.sum(recent[:, 0]))

        # ── 评分 ──────────────────────────────────────────────────
        bull_score = 0.0
        bear_score = 0.0
        choppy_score = 0.0
        crisis_score = 0.0

        # CRISIS：极端波动 + 极端放量
        if max_vol > _VOL_CRISIS_THRESHOLD:
            crisis_score += 0.7
        if max_vr > _VOLRATIO_HIGH:
            crisis_score += 0.3
        # vol 持续偏高
        if mean_vol > _VOL_NORMAL_MAX:
            crisis_score += 0.3

        # BULL：正收益 + 温和波动 + 温和放量
        if cum_ret > _RET_BULL_THRESHOLD:
            bull_score += 0.5
        elif cum_ret > _RET_BULL_THRESHOLD / 2:
            bull_score += 0.25
        if mean_vol < _VOL_NORMAL_MAX:
            bull_score += 0.2
        if mean_vr > 1.0 and mean_vr < 1.5:
            bull_score += 0.3  # 健康放量

        # BEAR：负收益 + 温和波动
        if cum_ret < _RET_BEAR_THRESHOLD:
            bear_score += 0.5
        elif cum_ret < _RET_BEAR_THRESHOLD / 2:
            bear_score += 0.25
        if mean_vol < _VOL_NORMAL_MAX:
            bear_score += 0.2
        # 熊市通常放量下跌
        if mean_vr > 1.0:
            bear_score += 0.2

        # CHOPPY：低波动 + 无明显趋势
        if abs(cum_ret) < _RET_BULL_THRESHOLD:
            choppy_score += 0.4
        if mean_vol < _VOL_CHOPPY_MAX:
            choppy_score += 0.4
        if max_vol < _VOL_NORMAL_MAX:
            choppy_score += 0.2

        # 互斥规则：crisis 出现时压制其他
        if crisis_score > 0.5:
            bull_score *= 0.3
            bear_score *= 0.3
            choppy_score *= 0.2

        # 互斥规则：强趋势时压制 choppy
        if abs(cum_ret) > _RET_BULL_THRESHOLD:
            choppy_score *= 0.4

        # Softmax 归一化（温度 1.0）
        scores = np.array([bull_score, bear_score, choppy_score, crisis_score], dtype=np.float64)
        scores = np.clip(scores, 0.0, None) + 0.05  # 平滑：每个状态给个 floor
        exp = np.exp(scores - scores.max())
        probs = exp / exp.sum()
        return probs

    def update(self, returns: np.ndarray, volumes: np.ndarray) -> RegimeInfo:
        """用最新 K 线数据更新状态估计"""
        features = self.compute_features(returns, volumes)
        self._state_probs = self._score_regimes(features)
        self._hidden_state = int(np.argmax(self._state_probs))

        regime_map = [Regime.BULL, Regime.BEAR, Regime.CHOPPY, Regime.CRISIS]
        regime = regime_map[self._hidden_state]
        descriptions = {
            Regime.BULL: "上涨趋势·顺势做多",
            Regime.BEAR: "下跌趋势·谨慎做空",
            Regime.CHOPPY: "震荡区间·高抛低吸",
            Regime.CRISIS: "极端波动·观望为主",
        }
        return RegimeInfo(
            regime=regime,
            confidence=float(self._state_probs[self._hidden_state]),
            regime_probs={
                regime_map[i]: float(self._state_probs[i])
                for i in range(self.N_REGIMES)
            },
            description=descriptions[regime],
        )

    def get_current(self) -> RegimeInfo:
        """返回当前状态（需先调用 update）"""
        if self._state_probs is None:
            return RegimeInfo(
                regime=Regime.CHOPPY,
                confidence=0.3,
                regime_probs={r: 0.25 for r in Regime},
                description="未初始化·默认震荡",
            )
        regime_map = [Regime.BULL, Regime.BEAR, Regime.CHOPPY, Regime.CRISIS]
        regime = regime_map[self._hidden_state]
        descriptions = {
            Regime.BULL: "上涨趋势·顺势做多",
            Regime.BEAR: "下跌趋势·谨慎做空",
            Regime.CHOPPY: "震荡区间·高抛低吸",
            Regime.CRISIS: "极端波动·观望为主",
        }
        return RegimeInfo(
            regime=regime,
            confidence=float(self._state_probs[self._hidden_state]),
            regime_probs={
                regime_map[i]: float(self._state_probs[i])
                for i in range(self.N_REGIMES)
            },
            description=descriptions[regime],
        )
