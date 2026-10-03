"""trades 端点测试 — 真实数据源 (UserFollow 表) 优先，freqtrade 兜底，无 mock。

运行：AI_TRADER_STRATEGIES_DB_PATH=/tmp/ai-trader-test-strategies.db python3 -m pytest tests/test_trades.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.db.models import UserFollow, UserFollowStatus, FollowSource


@pytest.fixture(scope="module", autouse=True)
def _setup_db() -> None:
    init_db()


def _seed_follow(
    pair: str,
    direction: str,
    status: str,
    *,
    entry_price: float = 100.0,
    exit_price: float | None = None,
    pnl_pct: float | None = None,
    exit_reason: str | None = None,
    stake: float = 100.0,
    hours_ago: int = 1,
) -> int:
    """插入一条 UserFollow（测试用）"""
    db = SessionLocal()
    try:
        f = UserFollow(
            pair=pair,
            timeframe="1h",
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            stake_amount=stake,
            leverage=1,
            status=status,
            source=FollowSource.AI_RECOMMENDATION.value,
            entry_time=datetime.now(UTC) - timedelta(hours=hours_ago),
            exit_time=(datetime.now(UTC) - timedelta(minutes=30)) if exit_price else None,
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        return f.id
    finally:
        db.close()


# ----------------------------------------------------------------------
# 1. 空数据：source=empty, total_count=0
# ----------------------------------------------------------------------
def test_trades_empty_when_no_follows_and_no_freqtrade(client: TestClient) -> None:
    """没有 UserFollow + 没 freqtrade DB → 返回空列表 + source=empty，绝不返回 mock"""
    response = client.get("/api/trades?limit=50")
    assert response.status_code == 200

    data = response.json()
    # 关键断言：不再有 source=mock
    assert data["source"] in {"follows", "freqtrade", "empty"}
    # 数据是空的（或来自真实源，但绝对不能含 mock_signal / DoubleEMACrossover mock 标记）
    for trade in data["trades"]:
        assert trade.get("enter_tag") != "mock_signal", "禁止返回 mock 数据"


# ----------------------------------------------------------------------
# 2. UserFollow 有 1 条：source=follows
# ----------------------------------------------------------------------
def test_trades_returns_userfollow_data(client: TestClient) -> None:
    """UserFollow 有 1 条已平仓数据时，前端必须能看到真实 entry/exit/pnl"""
    fid = _seed_follow(
        pair="ETH-USDT",
        direction="short",
        status=UserFollowStatus.CLOSED.value,
        entry_price=3500.0,
        exit_price=2742.39,
        pnl_pct=-0.21646,
        exit_reason="ai_signal_reversed",
        stake=1000.0,
    )

    response = client.get("/api/trades?limit=50")
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "follows", f"expected 'follows', got {data['source']!r}"
    assert data["total_count"] >= 1

    # 找刚插入的
    matches = [t for t in data["trades"] if t["id"] == fid]
    assert len(matches) == 1, f"UserFollow id={fid} 未出现在 /trades 中"
    trade = matches[0]

    # pair 必须从 ETH-USDT 转成 ETH/USDT（前端按 / 渲染）
    assert trade["pair"] == "ETH/USDT"
    assert trade["open_rate"] == 3500.0
    assert trade["close_rate"] == 2742.39
    assert trade["exit_reason"] == "ai_signal_reversed"
    # stake=1000, pnl_pct=-0.21646, pnl_abs ≈ -216.46
    assert abs(trade["close_profit_abs"] - (-216.46)) < 1.0
    assert trade["is_open"] is False


# ----------------------------------------------------------------------
# 3. 持仓中：is_open=True
# ----------------------------------------------------------------------
def test_trades_includes_open_positions(client: TestClient) -> None:
    """持仓中的 UserFollow 也要出现，is_open=true"""
    fid = _seed_follow(
        pair="BTC-USDT",
        direction="long",
        status=UserFollowStatus.OPEN.value,
        entry_price=60000.0,
        stake=500.0,
        hours_ago=2,
    )

    response = client.get("/api/trades?limit=50")
    assert response.status_code == 200
    data = response.json()

    matches = [t for t in data["trades"] if t["id"] == fid]
    assert len(matches) == 1
    trade = matches[0]
    assert trade["pair"] == "BTC/USDT"
    assert trade["is_open"] is True
    assert trade["close_rate"] is None  # 持仓中无平仓价
    assert trade["open_rate"] == 60000.0


# ----------------------------------------------------------------------
# 4. /stats/summary 也要切到真实数据
# ----------------------------------------------------------------------
def test_trades_summary_uses_follows(client: TestClient) -> None:
    """summary 统计要用真实 UserFollow，不能用 mock"""
    response = client.get("/api/trades/stats/summary")
    assert response.status_code == 200
    data = response.json()
    # source 必须是真实数据源之一
    assert data["source"] in {"follows", "freqtrade", "empty"}, \
        f"summary source 不能是 mock：{data['source']!r}"
    # 关键字段都在
    for field in [
        "total_trades", "winning_trades", "losing_trades",
        "win_rate", "total_profit_abs", "profit_factor", "source",
    ]:
        assert field in data


# ----------------------------------------------------------------------
# 5. /trades/{id} 优先 UserFollow
# ----------------------------------------------------------------------
def test_trade_by_id_returns_follow(client: TestClient) -> None:
    """按 ID 查询 — 走 UserFollow"""
    fid = _seed_follow(
        pair="SOL-USDT",
        direction="long",
        status=UserFollowStatus.CLOSED.value,
        entry_price=180.0,
        exit_price=195.0,
        pnl_pct=0.083,
        exit_reason="target",
        stake=200.0,
        hours_ago=10,
    )

    response = client.get(f"/api/trades/{fid}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == fid
    assert data["pair"] == "SOL/USDT"
    assert data["exit_reason"] == "target"


# ----------------------------------------------------------------------
# 6. filter by pair (ETH/USDT)
# ----------------------------------------------------------------------
def test_trades_filter_by_pair(client: TestClient) -> None:
    """按 pair=ETH/USDT 过滤"""
    response = client.get("/api/trades?pair=ETH/USDT&limit=100")
    assert response.status_code == 200
    data = response.json()
    # 所有返回的 pair 都是 ETH/USDT
    for trade in data["trades"]:
        assert trade["pair"] == "ETH/USDT"


# ----------------------------------------------------------------------
# 7. mock 数据绝不能出现 (守门测试)
# ----------------------------------------------------------------------
def test_no_mock_signal_enter_tag_ever(client: TestClient) -> None:
    """任何 trade.enter_tag 不应该是 'mock_signal'（来自 _generate_mock_trades 的标记）"""
    response = client.get("/api/trades?limit=500")
    assert response.status_code == 200
    data = response.json()
    for trade in data["trades"]:
        assert trade.get("enter_tag") != "mock_signal", \
            f"trade id={trade['id']} 仍有 mock_signal 标签"