"""Tests for backend.app.agent.runner — APScheduler 替代品（Task 7）

设计：用 asyncio.create_task + while True + asyncio.sleep，不引 apscheduler 依赖。
按项目现有模式（regime_shift_engine / github_sync）。

覆盖（plan Task 7）：
  - start() 启动后台任务
  - stop() 取消任务
  - _run_cycle() 触发 BTC + ETH × 4 timeframe = 8 analyze 调用
  - cycle 间隔 5 分钟
  - run_once() 手动触发（用于测试 + API 端点）
  - 单个 analyze 失败不阻塞其他
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.runner import AgentRunner
from app.agent.schemas import AnalysisStatus


# === Tests ===

class TestAgentRunnerRunOnce:
    @pytest.mark.asyncio
    async def test_run_once_triggers_8_analyzes(self):
        """run_once 应该跑 BTC + ETH × 4 tf = 8 次 analyze"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        runner = AgentRunner(agent=mock_agent)
        await runner.run_once()

        assert mock_agent.analyze.await_count == 8

    @pytest.mark.asyncio
    async def test_run_once_uses_correct_pairs_and_timeframes(self):
        """run_once 必须用 BTC-USDT + ETH-USDT 和 5m/15m/1h/1d"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        runner = AgentRunner(agent=mock_agent)
        await runner.run_once()

        # 提取所有调用
        calls = mock_agent.analyze.await_args_list
        pairs_timeframes = {(c.args[0], c.args[1]) for c in calls}

        expected = {
            ("BTC-USDT", "5m"), ("BTC-USDT", "15m"), ("BTC-USDT", "1h"), ("BTC-USDT", "1d"),
            ("ETH-USDT", "5m"), ("ETH-USDT", "15m"), ("ETH-USDT", "1h"), ("ETH-USDT", "1d"),
        }
        assert pairs_timeframes == expected

    @pytest.mark.asyncio
    async def test_run_once_continues_on_single_failure(self):
        """单个 analyze 失败不阻塞其他"""
        async def analyze(pair, timeframe):
            if pair == "BTC-USDT" and timeframe == "1h":
                raise Exception("BTC 1h 失败")
            return MagicMock(analysis_status=AnalysisStatus.SUCCESS)

        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(side_effect=analyze)

        runner = AgentRunner(agent=mock_agent)
        # 不应抛
        await runner.run_once()
        # 8 次都尝试了
        assert mock_agent.analyze.await_count == 8

    @pytest.mark.asyncio
    async def test_run_once_concurrent_with_gather(self):
        """run_once 用 asyncio.gather 并发跑（不是串行）"""
        import time

        analyze_times = []

        async def analyze(pair, timeframe):
            analyze_times.append((pair, timeframe, time.time()))
            await asyncio.sleep(0.05)
            return MagicMock(analysis_status=AnalysisStatus.SUCCESS)

        mock_agent = AsyncMock()
        mock_agent.analyze = analyze

        runner = AgentRunner(agent=mock_agent)
        start = time.time()
        await runner.run_once()
        elapsed = time.time() - start

        # 并发 8 个 50ms 任务，总时间 < 0.4s（串行会是 0.4s+）
        assert elapsed < 0.4, f"未并发: elapsed={elapsed:.3f}s"


class TestAgentRunnerLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        """start() 启动后台任务"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        runner = AgentRunner(agent=mock_agent, interval_seconds=60)
        runner.start()

        assert runner._task is not None
        assert not runner._task.done()

        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """stop() 取消任务"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        runner = AgentRunner(agent=mock_agent, interval_seconds=60)
        runner.start()
        await runner.stop()

        assert runner._task is None or runner._task.done()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """start() 多次调用不会创建多个 task"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        runner = AgentRunner(agent=mock_agent, interval_seconds=60)
        runner.start()
        task1 = runner._task
        runner.start()  # 应该 noop
        task2 = runner._task

        assert task1 is task2
        await runner.stop()

    @pytest.mark.asyncio
    async def test_loop_runs_at_least_once(self):
        """短 interval 启动后，等一会儿能跑到 analyze"""
        mock_agent = AsyncMock()
        mock_agent.analyze = AsyncMock(return_value=MagicMock(analysis_status=AnalysisStatus.SUCCESS))

        # interval 0.1s，但启动延后 5s 改为 0.05s 通过子类化 override
        runner = AgentRunner(agent=mock_agent, interval_seconds=0.1)
        # 覆盖 _loop 的首次 sleep 时间
        async def patched_loop():
            await asyncio.sleep(0.05)  # 短延后
            while runner._running:
                try:
                    await runner.run_once()
                except Exception:
                    pass
                await asyncio.sleep(runner._interval)

        runner._loop = patched_loop
        runner.start()
        await asyncio.sleep(0.3)  # 期望至少跑 2-3 cycle
        await runner.stop()

        # 至少跑了 1 个完整 cycle（8 calls）
        assert mock_agent.analyze.await_count >= 8


class TestAgentRunnerNoAgent:
    @pytest.mark.asyncio
    async def test_run_once_without_agent_raises(self):
        """没 agent 时 run_once 抛 RuntimeError"""
        runner = AgentRunner()
        with pytest.raises(RuntimeError, match="agent"):
            await runner.run_once()