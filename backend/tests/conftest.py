"""conftest — 共享 fixtures"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.data import binance_client


class _FakeRedis:
    """测试用 in-memory Redis mock（只支持 preferences 用到的 get/set/delete）"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试前自动注入 fake redis（preferences 端点依赖）"""
    fake = _FakeRedis()
    monkeypatch.setattr(binance_client, "_redis", fake, raising=False)
    yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client"""
    return TestClient(app)
