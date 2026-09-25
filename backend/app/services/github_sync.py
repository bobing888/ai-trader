"""GitHub 策略同步 — 每 6 小时自动 + 手动触发

通过 GitHub Search API 搜索 `crypto trading strategy language:python`，
按 star 数排序抓前 N 条。仓库根目录有 strategy.py 或 strategies/*.py 才会被采纳。
导入条目写入 SQLite，不覆盖已有的同 source 条目。
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.db.models import Strategy

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _extract_description(html_url: str, readme: str) -> str:
    """从 README 提取第一段非空文本作为策略描述"""
    if not readme:
        return ""
    # 去 markdown 链接和图片
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", readme)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 取第一段
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    first = paragraphs[0] if paragraphs else ""
    # 截断到 300 字符
    return first[:300]


async def search_strategies(query: str, limit: int) -> list[dict[str, Any]]:
    """GitHub REST search/repositories → list of {full_name, html_url, description, stars, ...}"""
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
        resp = await client.get(f"{GITHUB_API}/search/repositories", params=params)
        if resp.status_code != 200:
            logger.warning("GitHub search failed: %s %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        items = data.get("items", [])
        return [
            {
                "full_name": it["full_name"],
                "html_url": it["html_url"],
                "description": it.get("description") or "",
                "stars": it.get("stargazers_count", 0),
            }
            for it in items
        ]


async def fetch_strategy_code(full_name: str) -> str | None:
    """从仓库根目录拉 strategy.py 或第一段符合命名约定的 Python 文件源码"""
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
        # 先看根目录 contents
        resp = await client.get(f"{GITHUB_API}/repos/{full_name}/contents")
        if resp.status_code != 200:
            return None
        try:
            contents = resp.json()
        except ValueError:
            return None
        if not isinstance(contents, list):
            return None
        # 优先 strategy.py, 然后 strategies/*.py, 然后任何 .py
        candidates = [
            c for c in contents
            if c.get("type") == "file" and c.get("name", "").endswith(".py")
            and c.get("download_url")
        ]
        candidates.sort(key=lambda c: (
            0 if c["name"] == "strategy.py" else
            1 if c["name"].startswith("strategy") else
            2
        ))
        if not candidates:
            return None
        # 拉第一个候选文件（限制 100KB，避免巨型文件爆内存）
        url = candidates[0]["download_url"]
        if "?ref=" in url:
            url = url.split("?ref=")[0]
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        text = resp.text
        if len(text) > 100_000:
            text = text[:100_000] + "\n# truncated\n"
        return text


def _upsert(db: Session, item: dict[str, Any], code: str, description: str) -> bool:
    """插入或跳过（source 唯一）：返回 True=新增，False=跳过"""
    existing = db.query(Strategy).filter(
        Strategy.source == f"github:{item['full_name']}"
    ).first()
    if existing is not None:
        # 已存在则更新 description / code（如果变了）
        if existing.code != code or existing.description != description:
            existing.code = code
            existing.description = description or item["description"]
            existing.updated_at = datetime.now(timezone.utc)
        return False
    strategy = Strategy(
        name=f"github:{item['full_name']}",
        description=description or item["description"],
        strategy_type="github",
        source=f"github:{item['full_name']}",
        parameters={"stars": item["stars"]},
        code=code,
        status="enabled",
        weight=1.0,
    )
    db.add(strategy)
    return True


async def sync_github_strategies(db: Session) -> dict[str, Any]:
    """手动/定时同步入口"""
    if not settings.github_sync_enabled:
        return {"status": "disabled", "added": 0, "skipped": 0}
    try:
        items = await search_strategies(
            settings.github_search_query, settings.github_sync_limit
        )
    except Exception as e:
        logger.error("github search failed: %s", e)
        return {"status": "error", "error": str(e), "added": 0, "skipped": 0}

    added = 0
    skipped = 0
    for item in items:
        try:
            code = await fetch_strategy_code(item["full_name"])
            if not code:
                skipped += 1
                continue
            description = _extract_description(item["html_url"], "")
            if _upsert(db, item, code, description):
                added += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("skip %s: %s", item["full_name"], e)
            skipped += 1
    db.commit()
    return {
        "status": "ok",
        "added": added,
        "skipped": skipped,
        "total_searched": len(items),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


async def scheduled_sync_loop() -> None:
    """lifespan 启动后每 N 小时跑一次 sync。"""
    interval = max(1, settings.github_sync_interval_hours) * 3600
    # 首次启动延后 30 秒（等 app 起来 + db init）
    await asyncio.sleep(30)
    while True:
        try:
            with SessionLocal() as db:
                result = await sync_github_strategies(db)
                logger.info("github sync result: %s", result)
        except Exception as e:
            logger.error("github sync loop error: %s", e)
        await asyncio.sleep(interval)
