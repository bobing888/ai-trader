"""
数据源选择：
- BinanceClient: 通过 binance_client 单例访问（Binance 公开 REST API）
- OkxClient:    通过 okx_client 单例访问（OKX 公开 REST API）
  - 用 settings.data_source 决定 klines/ticker api 调用哪一份
  - 默认 binance（dyddd / 其他地区）
  - kbkkk（cognetcloud 香港 IP 被 Binance 限流）改 okx
"""
from .binance import BinanceClient, binance_client
from .okx import OkxClient, okx_client

__all__ = ["BinanceClient", "binance_client", "OkxClient", "okx_client"]


def get_client():
    """根据 settings.data_source 返回对应的 client 单例。"""
    from app.config import settings
    if (settings.data_source or "binance").lower() == "okx":
        return okx_client
    return binance_client
