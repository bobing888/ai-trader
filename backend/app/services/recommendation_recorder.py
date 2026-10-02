"""RecommendationRecorder — WS 1m K 线驱动推荐持久化（spec §4.1）

完整流程:
1. 启动时给每个 (pair, timeframe) 订阅 okx_ws_client.subscribe_candles(pair, "candle1m")
2. 每根 1m K 线 confirm=True → 缓存到 candles_1m[pair] (deque maxlen=200)
3. 触发 _scan_all_timeframes(pair): 对 5m/15m/1h/1d 重采样 → 算信号 → 写库 → 查 previous → emit bus
4. 同步调 SignalAggregator.aggregate()（不 await）

mock 模式（settings.use_mock_data=True）下整链跳过。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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
                self._candles_1m[pair] = deque(maxlen=200)
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
        """每条 1m K 线推送 → 缓存 → 触发 scan。"""
        while self._running:
            try:
                candle = await queue.get()
            except asyncio.CancelledError:
                break
            if not candle.get("confirm"):
                continue  # skip 未确认
            self._push_candle(pair, candle)
            await self._scan_all_timeframes(pair)

    def _push_candle(self, pair: str, candle: dict) -> None:
        buf = self._candles_1m.setdefault(pair, deque(maxlen=200))
        buf.append(candle)

    async def _scan_all_timeframes(self, pair: str) -> None:
        for tf in settings.recommendation_timeframes:
            try:
                await self._scan_one(pair, tf)
            except Exception as exc:
                logger.warning("[recorder] %s %s scan failed: %s", pair, tf, exc)

    async def _scan_one(self, pair: str, timeframe: str) -> None:
        """重采样 → 算推荐 → 写库 → emit bus（mock 跳过）。"""
        if settings.use_mock_data:
            return
        candles_1m = list(self._candles_1m.get(pair, []))
        if len(candles_1m) < 60:
            await self._write_no_data(pair, timeframe, "insufficient_1m_history")
            return
        candles = _resample_ohlcv(candles_1m, timeframe)
        if not candles or len(candles) < 30:
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
        """调 aggregator。同步（不 await）。"""
        from app.signals.aggregator import SignalAggregator
        from app.signals.regime import RegimeDetector
        from app.signals.strategy_pool import STRATEGY_INSTANCES

        regime_info = RegimeDetector().detect(candles, timeframe)
        strategy_results = [
            s.evaluate(candles, pair=pair, timeframe=timeframe)
            for s in STRATEGY_INSTANCES
        ]
        return SignalAggregator().aggregate(
            strategy_results,
            regime_info.regime,
            regime_info.confidence,
            timeframe,
        )

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
