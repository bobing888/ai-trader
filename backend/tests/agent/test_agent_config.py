"""Configuration tests for Trend Analysis Agent (Task 12)

覆盖：
  - settings.deepseek_api_key 缺省 ""
  - settings.agent_refresh_interval 缺省 300 (5m)
  - settings.agent_monthly_budget_cny 缺省 173.0
  - settings.agent_target_brier_score 缺省 0.25
  - settings.agent_target_direction_accuracy 缺省 0.6
  - DeepSeekProvider 接受显式 api_key 覆盖 settings
  - AgentRunner interval 可配置
"""

from __future__ import annotations


class TestAgentSettings:
    def test_settings_have_agent_defaults(self):
        """settings 应有所有 agent 配置缺省值"""
        from app.config import settings

        assert hasattr(settings, "deepseek_api_key")
        assert settings.deepseek_api_key == ""  # 默认空

        assert hasattr(settings, "deepseek_base_url")
        assert "deepseek" in settings.deepseek_base_url.lower()

        assert hasattr(settings, "deepseek_model")
        assert settings.deepseek_model == "deepseek-chat"

        assert hasattr(settings, "agent_refresh_interval")
        assert settings.agent_refresh_interval == 300  # 5m

        assert hasattr(settings, "agent_reasoning_timeout")
        assert settings.agent_reasoning_timeout == 30

        assert hasattr(settings, "agent_max_retries")
        assert settings.agent_max_retries == 2

        assert hasattr(settings, "agent_initial_backoff")
        assert settings.agent_initial_backoff == 0.5

        assert hasattr(settings, "agent_target_brier_score")
        assert settings.agent_target_brier_score == 0.25

        assert hasattr(settings, "agent_target_direction_accuracy")
        assert settings.agent_target_direction_accuracy == 0.6

        assert hasattr(settings, "agent_monthly_budget_cny")
        assert settings.agent_monthly_budget_cny == 173.0

    def test_settings_can_be_overridden_via_env(self, monkeypatch):
        """env var 可以覆盖 settings（pydantic-settings 标准行为）"""
        monkeypatch.setenv("AI_TRADER_DEEPSEEK_API_KEY", "sk-test-12345")
        monkeypatch.setenv("AI_TRADER_AGENT_REFRESH_INTERVAL", "120")

        from app.config import Settings
        s = Settings()

        assert s.deepseek_api_key == "sk-test-12345"
        assert s.agent_refresh_interval == 120


class TestProviderAcceptsConfig:
    def test_deepseek_provider_uses_settings_api_key_by_default(self):
        """没传 api_key → 用 settings.deepseek_api_key"""
        from unittest.mock import patch
        from app.config import Settings
        from app.agent.llm_client import DeepSeekProvider

        mock_settings = Settings(deepseek_api_key="sk-from-mock-settings")

        with patch("app.agent.llm_client.settings", mock_settings):
            provider = DeepSeekProvider()
            assert provider._api_key == "sk-from-mock-settings"

    def test_deepseek_provider_explicit_key_overrides_settings(self, monkeypatch):
        """显式传 api_key 覆盖 settings"""
        monkeypatch.setenv("AI_TRADER_DEEPSEEK_API_KEY", "sk-from-env")

        from app.agent.llm_client import DeepSeekProvider
        provider = DeepSeekProvider(api_key="sk-explicit")
        assert provider._api_key == "sk-explicit"

    def test_reasoner_uses_provider(self):
        """Reasoner 用 provider（且 timeout 可配）"""
        from unittest.mock import MagicMock
        from app.agent.reasoner import Reasoner
        provider = MagicMock()
        r = Reasoner(provider=provider, timeout=45)
        assert r._provider is provider
        assert r._timeout == 45


class TestAgentRunnerInterval:
    def test_runner_interval_default_5m(self):
        from app.agent.runner import AgentRunner, DEFAULT_INTERVAL_SECONDS
        assert DEFAULT_INTERVAL_SECONDS == 300
        runner = AgentRunner()
        assert runner._interval == 300

    def test_runner_interval_configurable(self):
        from app.agent.runner import AgentRunner
        runner = AgentRunner(interval_seconds=600)
        assert runner._interval == 600

    def test_runner_interval_from_settings(self):
        """通过 settings 配置 interval"""
        from app.config import settings
        from app.agent.runner import AgentRunner

        runner = AgentRunner(interval_seconds=settings.agent_refresh_interval)
        assert runner._interval == settings.agent_refresh_interval