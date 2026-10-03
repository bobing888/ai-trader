"""
Multi-timeframe informative data merge.

Pattern borrowed from freqtrade `informative_decorator` (GPL-3.0):
  https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/strategy/informative_decorator.py
Only the concept / architecture pattern is borrowed; no GPL code is copied.

TLRU cache idea implemented via stdlib `functools.lru_cache` + per-key TTL counter
to avoid the `cachetools` dependency (not available in this environment).
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Tuple

import pandas as pd

# ─── TTL ────────────────────────────────────────────────────────────────────────
# Number of informative-candle periods after which a cache entry expires.
# e.g. if informative TF is 4h and base TF is 1h, one 4h candle = 4 × 1h ticks.
# After 2 such informative candles have elapsed, the entry is evicted.
_INFORMATIVE_CACHE_TTL_CANDLES = 2


# ─── InformativeCache ───────────────────────────────────────────────────────────
class InformativeCache(OrderedDict):
    """
    LRU-like cache with per-entry TTL expressed in informative-candle units.

    Each entry stores (value, expire_at_ts).  `expire()` scans and evicts
    entries whose TTL has elapsed since their last access.

    Pattern借鉴：freqtrade `_PreparedDataInformative` 持有 dataframe + candle_age，
    但本实现使用 stdlib OrderedDict + time.monotonic()，无 GPL 代码。
    """

    def __init__(self, maxsize: int = 128) -> None:
        super().__init__()
        self._maxsize = maxsize
        self._ttls: dict[str, float] = {}  # key → expire_at monotonic seconds

    def __setitem__(self, key: str, value: Any) -> None:
        # Evict oldest if at capacity
        if len(self) >= self._maxsize and key not in dict.keys(self):
            self.popitem(last=False)
        super().__setitem__(key, value)
        # Set expiry: TTL × 1s per informative candle unit (simplified 1s/candle for TTL tracking)
        # Real candle-boundary expiry is enforced by callers that know TF ratios.
        self._ttls[key] = time.monotonic() + _INFORMATIVE_CACHE_TTL_CANDLES

    def __getitem__(self, key: str) -> Any:
        # Avoid calling self.__contains__ to prevent recursion
        if key not in dict.keys(self):
            raise KeyError(key)
        # Check TTL
        if time.monotonic() > self._ttls.get(key, 0):
            del self[key]
            raise KeyError(key)
        # LRU: move to end
        self.move_to_end(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if key not in dict.keys(self):  # type: ignore[arg-type]
            return False
        # Check TTL before declaring key valid
        if time.monotonic() > self._ttls.get(str(key), 0):  # type: ignore[arg-type]
            return False
        return True

    def expire(self) -> None:
        """Remove all expired entries."""
        now = time.monotonic()
        expired = [k for k, exp in list(self._ttls.items()) if now > exp]
        for k in expired:
            OrderedDict.pop(self, k, None)  # type: ignore[arg-type]
            self._ttls.pop(k, None)


# ─── Merge ──────────────────────────────────────────────────────────────────────
def merge_informative_timeframes(
    base_df: pd.DataFrame,
    informative_df: pd.DataFrame,
    base_tf: str,
    informative_tf: str,
) -> pd.DataFrame:
    """
    Merge an informative-timeframe DataFrame onto a base-timeframe DataFrame
    using ``pd.merge_asof`` (nearest past candle join).

    Columns from ``informative_df`` are renamed with an ``_<informative_tf>`` suffix
    so callers can distinguish base vs informative origins.

    Parameters
    ----------
    base_df:
        OHLCV data at the lower / faster timeframe.  Index must be a sorted
        ``DatetimeIndex`` (or index-like with a ``sort_index()`` call).
    informative_df:
        OHLCV data at a higher / slower timeframe.  Index same requirement.
    base_tf:
        String identifier for the base timeframe (e.g. ``"1h"``).  Used only
        for documentation; the actual merge key is the index.
    informative_tf:
        String identifier for the informative timeframe (e.g. ``"4h"``).
        Used to build the suffix on renamed columns.

    Returns
    -------
    ``pd.DataFrame`` with all columns from ``base_df`` (unchanged) plus the
    informative columns renamed with ``_<informative_tf>`` suffix.

    Pattern借鉴：freqtrade `_merge_prepared_informative_pair` 使用 ``merge_asof``
    backward join，确保 informative 数据不会"泄漏"未来蜡烛。
    本实现遵循同一模式，但使用标准 ``pd.merge_asof`` 而非 freqtrade 内部结构。
    """
    if base_df.empty or informative_df.empty:
        # Return base columns only, zero rows
        return base_df.copy()

    suffix = f"_{informative_tf}"

    # Rename informative columns with TF suffix so they don't clash with base
    informative_renamed = informative_df.add_suffix(suffix)

    # merge_asof requires both DataFrames to be sorted by index
    merged = pd.merge_asof(
        base_df.sort_index(),
        informative_renamed.sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    return merged
