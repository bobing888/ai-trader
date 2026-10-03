"""RecommendationRecorder — WS 1m K 线驱动推荐持久化（spec §4.1）

完整流程:
1. 启动时给每个 (pair, timeframe) 订阅 okx_ws_client.subscribe_candles(pair, "candle1m")
2. 每根 1m K 线 confirm=True → 缓存到 candles_1m[pair] (deque maxlen=300, OKX max)
3. 触发 _scan_all_timeframes(pair): 对 5m/15m/1h/1d 重采样 → 算信号 → 写库 → 查 previous → emit bus
4. 同步调 SignalAggregator.aggregate()（不 await）

mock 模式（settings.use_mock_data=True）下整链跳过。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from app.config import settings
from app.services.signal_change_bus import SignalChangeBus, SignalChangeEvent

if TYPE_CHECKING:

    from app.data.okx_ws import OkxWsClient
    from app.db.models import RecommendationHistory

logger = logging.getLogger(__name__)

_recorder: RecommendationRecorder | None = None

# timeframe → bucket 分钟
_BUCKET_MINUTES: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def _resample_ohlcv(
    candles_1m: list[dict[str, Any]], timeframe: str
) -> list[dict[str, Any]]:
    """从 1m OHLCV 重采样到目标 timeframe。

    1m K 线 ts 是毫秒；bucket ts = floor(ts / bucket_ms) * bucket_ms。
    bucket 内: open = 首根 o, high = max h, low = min l, close = 末根 c, vol = sum vol。
    """
    minutes = _BUCKET_MINUTES.get(timeframe)
    if minutes is None or not candles_1m:
        return []
    bucket_ms = minutes * 60 * 1000
    buckets: dict[int, dict[str, Any]] = {}
    for c in candles_1m:
        ts = c["ts"]
        bucket_ts = (ts // bucket_ms) * bucket_ms
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {
                "ts": bucket_ts,
                "o": c["o"],
                "h": c["h"],
                "l": c["l"],
                "c": c["c"],
                "vol": 0.0,
            }
        b = buckets[bucket_ts]
        b["h"] = max(b["h"], c["h"])
        b["l"] = min(b["l"], c["l"])
        b["c"] = c["c"]  # last seen close
        b["vol"] += c["vol"]
    return sorted(buckets.values(), key=lambda x: x["ts"])


class RecommendationRecorder:
    """每分钟持久化所有 (pair, timeframe) 推荐决议。"""

    def __init__(
        self,
        ws_client: OkxWsClient,
        bus: SignalChangeBus,
        session_factory: Any,
    ) -> None:
        self._ws = ws_client
        self._bus = bus
        self._session = session_factory
        self._running = False
        self._candle_queues: dict[str, asyncio.Queue] = {}
        self._candles_1m: dict[str, deque] = {}
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """启动 WS 订阅 + consume loop。"""
        if self._running:
            return
        if settings.use_mock_data:
            logger.info("[recorder] mock mode — skip")
            self._running = True
            return
        self._running = True
        for pair in settings.recommendation_pairs:
            try:
                q = await self._ws.subscribe_candles(pair, "candle1m")
                self._candle_queues[pair] = q
                # 2026-10-03: 提升到 300 (OKX max) 让 15m 重采样也够算 RSI(14)+EMA(21)
                self._candles_1m[pair] = deque(maxlen=300)
                self._tasks.append(asyncio.create_task(self._consume(pair, q)))
            except Exception as exc:
                logger.warning("[recorder] subscribe %s failed: %s", pair, exc)
        logger.info("[recorder] started for %d pairs", len(self._candle_queues))

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _consume(self, pair: str, queue: asyncio.Queue) -> None:
        """每条 1m K 线推送 → 缓存 → 触发 scan。

        WS fallback (kbkkk.com 2026-10-03):
          OKX V5 公共 WS candle* 整体 60018 (channel doesn't exist) — 数据不会来。
          30s 内 queue 没数据 → 自动切 REST polling 每 60s 拉 1m K 线, 直到 WS 修好。
          WS 修好后, REST polling 检测到 WS 有数据 → 自动停 polling, 回到 WS。
        """
        from app.data.okx import okx_client

        ws_last_seen = time.monotonic()
        rest_polling_active = False

        while self._running:
            # 优先等 WS 推送（timeout=2s, 让 fallback 检测能跑）
            try:
                candle = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                candle = None
            except asyncio.CancelledError:
                break

            if candle is not None:
                # WS alive, 走正常路径
                ws_last_seen = time.monotonic()
                if rest_polling_active:
                    logger.info("[recorder] %s: WS 恢复, 停 REST polling", pair)
                    rest_polling_active = False
                if not candle.get("confirm"):
                    continue
                self._push_candle(pair, candle)
                await self._scan_all_timeframes(pair)
                continue

            # WS 2s 内无推送 — 检查是否要切 REST fallback
            now = time.monotonic()
            if (now - ws_last_seen) > 30.0 and not rest_polling_active:
                logger.warning(
                    "[recorder] %s: WS 30s 无数据, 启用 REST polling fallback "
                    "(kbkkk.com OKX V5 candle* WS 已知 60018 拒订阅)",
                    pair,
                )
                rest_polling_active = True

            if rest_polling_active:
                try:
                    # 2026-10-03: 提到 300 (OKX max) 让 15m 也够算 RSI
                    klines = await okx_client.get_klines(pair, "1m", 300)
                except Exception as exc:
                    logger.warning("[recorder] %s REST klines failed: %s", pair, exc)
                    await asyncio.sleep(60)
                    continue
                # 转成 candles_1m 格式
                self._candles_1m[pair] = deque(
                    (
                        {
                            "ts": int(k["time"]) * 1000,
                            "o": k["open"],
                            "h": k["high"],
                            "l": k["low"],
                            "c": k["close"],
                            "vol": k["volume"],
                            "confirm": True,
                        }
                        for k in reversed(klines)  # get_klines 返回倒序, 还原成时间升序
                    ),
                    maxlen=300,
                )
                # 仅在最近 1 根 confirm 时触发 scan
                if klines and len(klines) > 0:
                    await self._scan_all_timeframes(pair)
                await asyncio.sleep(60)

    def _push_candle(self, pair: str, candle: dict) -> None:
        buf = self._candles_1m.setdefault(pair, deque(maxlen=300))
        buf.append(candle)

    async def _scan_all_timeframes(self, pair: str) -> None:
        for tf in settings.recommendation_timeframes:
            try:
                await self._scan_one(pair, tf)
            except Exception as exc:
                logger.warning("[recorder] %s %s scan failed: %s", pair, tf, exc)

    async def _fetch_candles_direct(self, pair: str, timeframe: str) -> list[dict[str, Any]]:
        """直接 REST 拉目标 timeframe 的 K 线（用于 1h/1d）。

        OKX 1 次最多 300 根 → 1h = 12.5 天 / 1d = 10 个月，足够 RSI(14) + EMA(21)。
        转 candles 格式与 _resample_ohlcv 输出对齐: {ts, o, h, l, c, vol}。
        """
        from app.data.okx import okx_client

        try:
            klines = await okx_client.get_klines(pair, timeframe, 300)
        except Exception as exc:
            logger.warning("[recorder] %s %s REST klines failed: %s", pair, timeframe, exc)
            return []
        # get_klines 返回倒序 → 翻成时间升序
        return [
            {
                "ts": int(k["time"]) * 1000,
                "o": k["open"],
                "h": k["high"],
                "l": k["low"],
                "c": k["close"],
                "vol": k["volume"],
            }
            for k in reversed(klines)
        ]

    async def _scan_one(self, pair: str, timeframe: str) -> None:
        """重采样 → 算推荐 → 写库 → emit bus（mock 跳过）。

        2026-10-03 修复 (B 任务后续):
          - 5m/15m 仍走 candles_1m 重采样（200 根 1m = 5h 历史够算 RSI(14)）
          - 1h/1d 走 REST 直接拉该周期 K 线（OKX 1 次 300 根 = 1h 12.5d / 1d 10mo，
            远超 RSI(14) 需要 15 桶 + EMA(21) 需要 21 桶）
        """
        if settings.use_mock_data:
            return

        # 1h/1d 用粗粒度历史（不依赖 1m 重采样）
        if timeframe in ("1h", "1d"):
            candles = await self._fetch_candles_direct(pair, timeframe)
        else:
            candles_1m = list(self._candles_1m.get(pair, []))
            if len(candles_1m) < 60:
                await self._write_no_data(pair, timeframe, "insufficient_1m_history")
                return
            candles = _resample_ohlcv(candles_1m, timeframe)
        if not candles or len(candles) < 21:
            await self._write_no_data(pair, timeframe, "resample_too_short")
            return

        try:
            signal = self._compute_signal(pair, timeframe, candles)
        except Exception as exc:
            await self._write_error(pair, timeframe, str(exc))
            return

        record = self._build_record(pair, timeframe, signal)
        db = self._session()
        try:
            db.add(record)
            db.commit()
            db.refresh(record)
            # 查 previous
            from app.db.models import RecommendationHistory

            previous = (
                db.query(RecommendationHistory)
                .filter(
                    RecommendationHistory.pair == pair,
                    RecommendationHistory.timeframe == timeframe,
                    RecommendationHistory.scanned_at < record.scanned_at,
                )
                .order_by(RecommendationHistory.scanned_at.desc())
                .first()
            )
        finally:
            db.close()

        change_type = _classify_change(previous, record)
        if change_type != "no_change":
            await self._bus.emit(
                SignalChangeEvent(
                    pair=pair,
                    timeframe=timeframe,
                    previous=previous,
                    current=record,
                    change_type=change_type,
                )
            )

    def _compute_signal(self, pair: str, timeframe: str, candles: list[dict]):
        """调 aggregator。同步（不 await）。

        D1: 传 candles + current_price 让 aggregator 算 ATR + entry levels.
        """
        from app.signals.aggregator import SignalAggregator
        from app.signals.regime import RegimeDetector
        from app.signals.strategy_pool import STRATEGY_INSTANCES

        regime_info = RegimeDetector().detect(candles, timeframe)

        # recorder 调用 strategy 的正确姿势 (与 api/signals.py 一致):
        #   evaluate(candles_dict 含 symbol/timeframe/close/..., volumes, regime)
        candles_dict = {
            "symbol": pair,
            "timeframe": timeframe,
            "close": [c.get("c", c.get("close", 0.0)) for c in candles],
            "open": [c.get("o", c.get("open", 0.0)) for c in candles],
            "high": [c.get("h", c.get("high", 0.0)) for c in candles],
            "low": [c.get("l", c.get("low", 0.0)) for c in candles],
        }
        volumes = np.array([c.get("vol", c.get("volume", 1.0)) for c in candles], dtype=np.float64)
        strategy_results = [
            s.evaluate(candles_dict, volumes, regime_info.regime.value)
            for s in STRATEGY_INSTANCES.values()
        ]

        # D1: 转成 aggregator 期望的字段名 (open/high/low/close + open_time)
        ohlcv_for_agg = self._to_ohlcv(candles)
        current_price = candles[-1]["c"] if candles else None
        return SignalAggregator().aggregate(
            strategy_results,
            regime_info.regime,
            regime_info.confidence,
            timeframe,
            candles_dict={pair: ohlcv_for_agg},
            current_price={pair: current_price},
            adx=regime_info.adx,
            hurst=regime_info.hurst,
        )

    @staticmethod
    def _to_ohlcv(candles: list[dict]) -> list[dict]:
        """把 resampled {ts, o, h, l, c, vol} 转 aggregator 期望的 {open, high, low, close, open_time, volume}."""
        from datetime import UTC, datetime
        out = []
        for c in candles:
            ts_ms = c.get("ts", 0)
            try:
                ot = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
            except Exception:
                ot = datetime.now(UTC)
            out.append(
                {
                    "open_time": ot,
                    "open": float(c.get("o", 0.0)),
                    "high": float(c.get("h", 0.0)),
                    "low": float(c.get("l", 0.0)),
                    "close": float(c.get("c", 0.0)),
                    "volume": float(c.get("vol", 0.0)),
                }
            )
        return out

    def _build_record(self, pair: str, timeframe: str, signal) -> RecommendationHistory:
        from app.db.models import RecommendationHistory, RecommendationOutcome

        if signal is None:
            return RecommendationHistory(
                pair=pair,
                timeframe=timeframe,
                has_signal=False,
                direction=None,
                confidence=None,
                regime=None,
                regime_confidence=None,
                outcome=RecommendationOutcome.NO_SIGNAL.value,
                scanned_at=datetime.now(UTC),
                source="okx",
            )

        import json

        return RecommendationHistory(
            pair=pair,
            timeframe=timeframe,
            has_signal=True,
            direction=signal.direction,
            confidence=signal.confidence,
            regime=signal.regime,
            regime_confidence=signal.regime_confidence,
            contributing_strategies=json.dumps(signal.contributing_strategies),
            reasons=json.dumps(signal.reasons),
            suggested_leverage=signal.suggested_leverage,
            min_agreement_used=signal.min_agreement_used,
            fast_path=signal.fast_path,
            outcome=RecommendationOutcome.HAS_SIGNAL.value,
            scanned_at=datetime.now(UTC),
            source="okx",
            # Phase 1
            calibrated_confidence=signal.calibrated_confidence,
            net_pnl_estimate=signal.net_pnl_estimate,
            # D1: executable levels
            entry_levels_json=json.dumps(signal.entry_levels) if signal.entry_levels else None,
            stop_loss_price=signal.stop_loss_price,
            take_profit_1_price=signal.take_profit_1_price,
            take_profit_2_price=signal.take_profit_2_price,
            atr=signal.atr,
            risk_reward_ratio=signal.risk_reward_ratio,
            current_price=(
                signal.entry_levels[0]["price"] if signal.entry_levels else None
            ),
            # D2: quality gate
            quality=signal.quality,
            quality_reasons_json=(
                json.dumps(signal.quality_reasons) if signal.quality_reasons else None
            ),
            # 2026-10-03: 进/离场时间窗口
            entry_window_minutes=signal.entry_window_minutes,
            exit_window_minutes=signal.exit_window_minutes,
        )

    async def _write_no_data(self, pair: str, timeframe: str, reason: str) -> None:
        from app.db.models import RecommendationHistory, RecommendationOutcome

        record = RecommendationHistory(
            pair=pair,
            timeframe=timeframe,
            has_signal=False,
            direction=None,
            confidence=None,
            regime=None,
            regime_confidence=None,
            outcome=RecommendationOutcome.NO_DATA.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        db = self._session()
        try:
            db.add(record)
            db.commit()
        finally:
            db.close()
        logger.debug("[recorder] %s %s NO_DATA: %s", pair, timeframe, reason)

    async def _write_error(self, pair: str, timeframe: str, err: str) -> None:
        from app.db.models import RecommendationHistory, RecommendationOutcome

        record = RecommendationHistory(
            pair=pair,
            timeframe=timeframe,
            has_signal=False,
            direction=None,
            confidence=None,
            regime=None,
            regime_confidence=None,
            outcome=RecommendationOutcome.ERROR.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        db = self._session()
        try:
            db.add(record)
            db.commit()
        finally:
            db.close()
        logger.warning("[recorder] %s %s ERROR: %s", pair, timeframe, err)


def _classify_change(previous, current) -> str:
    """判断变化类型。"""
    if previous is None:
        return "first_emit"
    if previous.direction != current.direction:
        return "direction"
    if previous.regime != current.regime:
        return "regime"
    if (
        previous.confidence is not None
        and current.confidence is not None
        and abs(previous.confidence - current.confidence) > 0.15
    ):
        return "confidence"
    if previous.has_signal and not current.has_signal:
        return "no_signal"
    return "no_change"


def set_recorder(r: RecommendationRecorder) -> None:
    global _recorder
    _recorder = r


def get_recorder() -> RecommendationRecorder:
    if _recorder is None:
        raise RuntimeError("RecommendationRecorder not initialized")
    return _recorder
