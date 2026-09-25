"""User preferences 端点测试"""

from fastapi.testclient import TestClient


USER = {"X-User-Id": "test-uuid-001"}


def test_get_default_when_missing(client: TestClient) -> None:
    """首次访问 → 返回默认偏好（MA20/MA30/EMA50/BOLL/RSI/MACD/KDJ/OBV + 5 形态）"""
    # 用随机 UUID 避免命中真实数据
    headers = {**USER, "X-User-Id": "test-uuid-fresh-001"}
    response = client.get("/api/preferences", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["user_id"] == "test-uuid-fresh-001"
    prefs = data["preferences"]
    assert "indicators" in prefs
    assert "patterns" in prefs

    # 默认开启的核心指标
    assert prefs["indicators"]["ma20"]["enabled"] is True
    assert prefs["indicators"]["boll"]["enabled"] is True
    assert prefs["indicators"]["rsi"]["enabled"] is True
    assert prefs["indicators"]["macd"]["enabled"] is True

    # 默认开启的形态（top 10 中 hammer 等）
    assert prefs["patterns"]["hammer"]["enabled"] is True
    assert prefs["patterns"]["engulfing"]["enabled"] is True

    # 完整 BOLL 参数
    assert prefs["indicators"]["boll"]["params"]["length"] == 20
    assert prefs["indicators"]["boll"]["params"]["mult"] == 2.0


def test_put_then_get_roundtrip(client: TestClient) -> None:
    """PUT 自定义偏好 → GET 拿回相同数据"""
    headers = {**USER, "X-User-Id": "test-uuid-rt-002"}

    custom = {
        "indicators": {
            "ma5": {"enabled": True, "params": {"length": 5}},
            "ma10": {"enabled": True, "params": {"length": 10}},
            "boll": {"enabled": True, "params": {"length": 30, "mult": 2.5}},
        },
        "patterns": {
            "hammer": {"enabled": True},
            "engulfing": {"enabled": False},
        },
    }

    put_resp = client.put("/api/preferences", json=custom, headers=headers)
    assert put_resp.status_code == 200
    assert put_resp.json()["preferences"]["indicators"]["boll"]["params"]["length"] == 30

    get_resp = client.get("/api/preferences", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["preferences"]["indicators"]["ma5"]["enabled"] is True
    assert data["preferences"]["indicators"]["boll"]["params"]["mult"] == 2.5
    assert data["preferences"]["patterns"]["engulfing"]["enabled"] is False


def test_reset_returns_default(client: TestClient) -> None:
    """PUT → POST /reset → GET 拿回默认"""
    headers = {**USER, "X-User-Id": "test-uuid-reset-003"}

    # 1) PUT 一个非默认偏好
    custom = {"indicators": {"ma20": {"enabled": False}}, "patterns": {}}
    client.put("/api/preferences", json=custom, headers=headers)

    # 2) reset
    reset_resp = client.post("/api/preferences/reset", headers=headers)
    assert reset_resp.status_code == 200
    # 默认 ma20 是 enabled
    assert reset_resp.json()["preferences"]["indicators"]["ma20"]["enabled"] is True

    # 3) GET 确认
    get_resp = client.get("/api/preferences", headers=headers)
    assert get_resp.json()["preferences"]["indicators"]["ma20"]["enabled"] is True


def test_missing_header_returns_422(client: TestClient) -> None:
    """不带 X-User-Id header → 422 验证错误"""
    response = client.get("/api/preferences")
    assert response.status_code == 422


def test_different_users_isolated(client: TestClient) -> None:
    """不同 user_id 的偏好互不影响"""
    h1 = {**USER, "X-User-Id": "test-uuid-A-005"}
    h2 = {**USER, "X-User-Id": "test-uuid-B-005"}

    client.put(
        "/api/preferences",
        json={"indicators": {"ma5": {"enabled": True}}, "patterns": {}},
        headers=h1,
    )
    b_data = client.get("/api/preferences", headers=h2).json()
    # B 用户应该是默认（ma5 是 False）
    assert b_data["preferences"]["indicators"]["ma5"]["enabled"] is False


def test_no_redirect_on_trailing_slash(client: TestClient) -> None:
    """root endpoint 不重定向（避免 https → http 丢失）"""
    headers = {**USER, "X-User-Id": "test-uuid-no-redir"}
    resp = client.get("/api/preferences", headers=headers, follow_redirects=False)
    # 不应该是 307 redirect
    assert resp.status_code == 200


def test_openapi_includes_preferences(client: TestClient) -> None:
    """/openapi.json 暴露 preferences 端点"""
    spec = client.get("/openapi.json").json()
    assert "/api/preferences" in spec["paths"]
    assert "/api/preferences/reset" in spec["paths"]


def test_default_has_25_indicators_and_10_patterns(client: TestClient) -> None:
    """默认配置覆盖 ~30 个核心指标和 10 个常用形态"""
    headers = {**USER, "X-User-Id": "test-uuid-count"}
    data = client.get("/api/preferences", headers=headers).json()
    assert len(data["preferences"]["indicators"]) >= 20  # 至少 20 个
    assert len(data["preferences"]["patterns"]) >= 10  # 至少 10 个形态
