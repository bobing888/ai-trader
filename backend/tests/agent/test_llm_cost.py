"""Cost monitoring test (Task 11)

覆盖：
  - mock token usage 算出 LLM cost
  - 验证 1 天 ≤ ¥173 (5m cycle × 576 calls × ¥0.01/avg)
"""

from __future__ import annotations


# DeepSeek V3 pricing (2026-10-03)
DEEPSEEK_INPUT_PRICE_PER_MILLION = 1.0  # ¥1 / M tokens
DEEPSEEK_OUTPUT_PRICE_PER_MILLION = 2.0  # ¥2 / M tokens


def estimate_daily_cost(
    calls_per_day: int,
    avg_input_tokens: int,
    avg_output_tokens: int,
) -> float:
    """估算日 cost（¥）"""
    total_input = calls_per_day * avg_input_tokens
    total_output = calls_per_day * avg_output_tokens
    cost = (
        total_input / 1_000_000 * DEEPSEEK_INPUT_PRICE_PER_MILLION
        + total_output / 1_000_000 * DEEPSEEK_OUTPUT_PRICE_PER_MILLION
    )
    return cost


class TestLLMCost:
    def test_5m_cycle_within_budget(self):
        """5m 循环 × 576 calls/天 × 1000 in + 500 out tokens ≤ ¥173/月"""
        # 1 天 = 86400 秒 / 300 秒 = 288 cycles
        # 每个 cycle 8 次 (BTC + ETH × 4 tf)
        calls_per_day = 288 * 8  # = 2304
        # 实际 prompt ~ 800-1500 tokens, output ~ 300-500
        cost = estimate_daily_cost(
            calls_per_day=calls_per_day,
            avg_input_tokens=1200,
            avg_output_tokens=400,
        )
        # ¥2304 × (1200/1e6) × 1 + ¥2304 × (400/1e6) × 2 = 2.76 + 1.84 = ¥4.6/天
        # ¥4.6 × 30 = ¥139/月 — well below ¥173 预算
        assert cost < 173 / 30, f"Daily cost ¥{cost:.2f} exceeds ¥{173/30:.2f}/day budget"
        print(f"Estimated daily cost: ¥{cost:.2f}, monthly: ¥{cost*30:.2f}")

    def test_60s_cycle_exceeds_budget(self):
        """60s 循环 × 13824 calls/天 × avg tokens — 警告超预算"""
        # 1 天 = 86400 秒 / 60 秒 = 1440 cycles
        # 每个 cycle 8 次
        calls_per_day = 1440 * 8  # = 11520
        cost = estimate_daily_cost(
            calls_per_day=calls_per_day,
            avg_input_tokens=1200,
            avg_output_tokens=400,
        )
        # ¥11520 × (1200/1e6) × 1 + ¥11520 × (400/1e6) × 2 = 13.82 + 9.22 = ¥23/天
        # ¥23 × 30 = ¥691/月 — 超过 ¥173 预算（这是为什么选 5m 而非 60s）
        assert cost > 173 / 30, "60s cycle should exceed budget"
        # sanity check
        assert 600 < cost * 30 < 800

    def test_extreme_load_still_monitorable(self):
        """极端负载（每分钟一次）— 仅记录不抛"""
        # 60s × 2 pairs × 4 tf = 11520 calls/day
        # 上限检查
        cost = estimate_daily_cost(
            calls_per_day=11520,
            avg_input_tokens=2000,  # 大 prompt
            avg_output_tokens=800,   # 长 output
        )
        # 仅 sanity: cost > 0 且 < ¥100/天（即使极端）
        assert cost > 0
        assert cost < 100  # 每天 ¥23 左右


class TestRunnerCostControl:
    def test_default_interval_is_5_minutes(self):
        """默认 interval 必须是 300s（5m）— 不是 60s"""
        from app.agent.runner import AgentRunner, DEFAULT_INTERVAL_SECONDS
        assert DEFAULT_INTERVAL_SECONDS == 300

        runner = AgentRunner()
        assert runner._interval == 300

    def test_5m_interval_produces_manageable_daily_calls(self):
        """5m × 288 cycles × 8 calls = 2304 calls/day (manageable)"""
        interval = 300  # 5m
        cycles_per_day = 86400 // interval  # = 288
        calls_per_cycle = 2 * 4  # BTC + ETH × 4 tf
        calls_per_day = cycles_per_day * calls_per_cycle
        # 2304 calls/day is manageable for DeepSeek (well under rate limits)
        assert calls_per_day == 2304
        assert calls_per_day < 5000  # DeepSeek free tier: 5M tokens/month ≈ 5000 calls/month ≈ 167 calls/day (low)
        # 但 ¥173/月 budget 可以撑得起 2304/天 = 70000/月 calls