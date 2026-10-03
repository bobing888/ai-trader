"""conftest — 共享 fixtures"""

import os
import sys
from pathlib import Path

# 在 app 导入前覆盖 DB 路径，避免 ROFS /app/ 系统上失败
# 使用绝对路径，避开 session._resolve_db_path 的 /app/data fallback
_test_db = Path(__file__).resolve().parent.parent / "data" / "test_strategies.db"
_test_db.parent.mkdir(parents=True, exist_ok=True)
os.environ["AI_TRADER_STRATEGIES_DB_PATH"] = str(_test_db.resolve())
os.environ["AI_TRADER_GITHUB_SYNC_ENABLED"] = "false"  # 测试中关闭 github sync 后台任务
# 测试期默认走 mock 数据源（避免 CI 调真 OKX/Binance 公开 API 限流）
os.environ.setdefault("AI_TRADER_USE_MOCK_DATA", "true")

import pytest

# 在 app 导入后立即初始化 DB（确保 BacktestRun/BacktestTrade 表存在）
def _ensure_init_db() -> None:
    try:
        from app.db.session import init_db
        init_db()
    except Exception:
        pass

# Guard: app.main may fail to import on ROFS systems (macOS /app/ ROFS).
# When it does, skip fixtures that depend on it but still allow
# standalone tests (e.g. regime_shift_engine, notification_service).
try:
    from fastapi.testclient import TestClient

    from app.data import binance_client
    from app.main import app
    _APP_AVAILABLE = True
    _ensure_init_db()
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
    from app.db.session import init_db
    init_db()
    return TestClient(app)
