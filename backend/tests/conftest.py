"""conftest — 共享 fixtures"""

import pytest

# Guard: app.main may fail to import on ROFS systems (macOS /app/ ROFS).
# When it does, skip fixtures that depend on it but still allow
# standalone tests (e.g. regime_shift_engine, notification_service).
try:
    from fastapi.testclient import TestClient

    from app.data import binance_client
    from app.main import app
    _APP_AVAILABLE = True
except OSError:
    # ROFS /app/ — app.main can't be imported; skip client fixture
    _APP_AVAILABLE = False
    app = None  # type: ignore[assignment]


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
    if not _APP_AVAILABLE:
        yield
        return
    fake = _FakeRedis()
    monkeypatch.setattr(binance_client, "_redis", fake, raising=False)
    yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client"""
    if not _APP_AVAILABLE:
        pytest.skip("app.main not available on this system (ROFS /app/)")
    return TestClient(app)
