"""Tests for lifespan integration — AgentRunner lifecycle (Task 9)

覆盖：
  - main.py 在 import 时加载 agent 模块（不抛）
  - TrendAgent / AgentRunner / DeepSeekProvider 都可实例化
  - lifespan 的 agent 段代码语法/导入正确（不实际跑 lifespan）
"""

from __future__ import annotations


class TestMainModuleImports:
    def test_main_imports_clean(self):
        """app.main 应能 import（包含所有路由 + lifespan）"""
        from app.main import app, lifespan
        assert app is not None
        assert lifespan is not None

    def test_agent_router_registered(self):
        """AgentRouter 应该注册到 main app"""
        from app.main import app

        # app.routes 可能不含 include_router 加入的子路由
        # 用 OpenAPI schema 验证（最可靠）
        schema = app.openapi()
        paths = schema.get("paths", {})
        agent_paths = [p for p in paths if p.startswith("/api/agent")]
        assert len(agent_paths) >= 3, f"agent routes missing: {agent_paths}"


class TestAgentComponentConstruction:
    """确认 lifespan 中要用的对象都能构造"""

    def test_construct_trend_agent(self):
        from app.agent import TrendAgent
        from app.agent.reasoner import Reasoner
        from app.agent.llm_client import DeepSeekProvider

        provider = DeepSeekProvider(api_key="")
        reasoner = Reasoner(provider=provider)
        agent = TrendAgent(reasoner=reasoner)
        assert agent is not None

    def test_construct_agent_runner(self):
        from app.agent import TrendAgent
        from app.agent.runner import AgentRunner
        from app.agent.llm_client import DeepSeekProvider
        from app.agent.reasoner import Reasoner

        provider = DeepSeekProvider(api_key="")
        reasoner = Reasoner(provider=provider)
        agent = TrendAgent(reasoner=reasoner)
        runner = AgentRunner(agent=agent)
        assert runner is not None
        assert runner._agent is agent