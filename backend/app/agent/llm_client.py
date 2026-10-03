"""LLM Provider — LLM 抽象层（Task 4）.

设计：
  - LLMProvider Protocol：任何有 .complete(system, user, **kw) → str 的对象
  - DeepSeekProvider：DeepSeek V3 实现（OpenAI-compatible API）
  - 后续可加 QwenProvider / ClaudeProvider / LocalOllamaProvider

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §6.3
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# === Protocol ===

class LLMProvider(Protocol):
    """LLM Provider 抽象接口"""

    async def complete(self, system: str, user: str, **kw: Any) -> str:
        """调 LLM 返回 string（JSON string 格式由调用方解析）"""
        ...


# === DeepSeek Provider ===

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_CHAT_COMPLETIONS = "/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"  # DeepSeek V3
DEEPSEEK_TIMEOUT_SECONDS = 30.0


class DeepSeekProvider:
    """DeepSeek V3 Provider (OpenAI-compatible API)

    配置：
      DEEPSEEK_API_KEY 从 app.config.settings 读
      模型：deepseek-chat（V3）
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEEPSEEK_DEFAULT_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
        timeout: float = DEEPSEEK_TIMEOUT_SECONDS,
    ) -> None:
        # 优先用显式传的 key，回退到 settings
        self._api_key = api_key or getattr(settings, "deepseek_api_key", "")
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    async def complete(self, system: str, user: str, **kw: Any) -> str:
        """调 DeepSeek Chat Completions API

        Returns:
            LLM 返回的 string content（调用方负责解析 JSON）

        Raises:
            RuntimeError: API key 未配置
            httpx.HTTPStatusError: DeepSeek 4xx/5xx
            httpx.TimeoutException: 超时
        """
        if not self._api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY 未配置。在 .env 加 deepseek_api_key=<your_key> 或显式传给 DeepSeekProvider(api_key=...)"
            )

        url = f"{self._base_url}{DEEPSEEK_CHAT_COMPLETIONS}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": kw.get("temperature", 0.3),
            "max_tokens": kw.get("max_tokens", 2000),
            "response_format": {"type": "json_object"},  # 强制 JSON 输出
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        # OpenAI-compatible: choices[0].message.content
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error(f"DeepSeek 响应格式异常: {data}")
            raise RuntimeError(f"DeepSeek 响应格式异常: {e}") from e

        return content


# === Helper: parse JSON from LLM response (with code-block extraction) ===

def extract_json_from_response(text: str) -> dict | None:
    """从 LLM 返回中提取 JSON

    支持：
      - 纯 JSON: {"regime": "bull", ...}
      - Markdown code block: ```json\n{...}\n```
      - 文本包裹 JSON: "分析: {...}"
    """
    text = text.strip()

    # 1. 尝试 Markdown code block
    if "```" in text:
        # 找第一个 code block
        start = text.find("```")
        end = text.find("```", start + 3)
        if end > start:
            inner = text[start + 3:end].strip()
            # 去掉可能的语言标签
            if inner.startswith("json"):
                inner = inner[4:].strip()
            text = inner

    # 2. 找第一个 { 和最后一个 }
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start == -1 or brace_end == -1 or brace_end < brace_start:
        return None

    candidate = text[brace_start : brace_end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None