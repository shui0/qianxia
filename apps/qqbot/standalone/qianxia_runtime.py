import asyncio
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import sys

from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from pydantic import BaseModel, Field
from qianxia_state import Memory

APPS = Path(__file__).resolve().parents[2]


class GroupConfig(BaseModel):
    qianxia_groups: set[int] = Field(default_factory=set)
    qianxia_memory_groups: set[int] = Field(default_factory=set)
    qianxia_memory_path: Path = APPS.parent / "qq-memory/standalone.sqlite3"


@lru_cache(maxsize=1)
def group_config() -> GroupConfig:
    return get_plugin_config(GroupConfig)


@lru_cache(maxsize=1)
def memory_store() -> Memory:
    return Memory(group_config().qianxia_memory_path)


def allowed(event: MessageEvent) -> bool:
    groups = group_config().qianxia_groups
    return event.user_id != event.self_id and (
        not isinstance(event, GroupMessageEvent) or not groups or event.group_id in groups
    )


def command(name: str, *, aliases: set[str] | None = None):
    return on_command(name, aliases=aliases, rule=allowed, priority=10, block=True)


async def run_cli(app: str, args: list[str], timeout: float = 25, *, output_limit: int | None = 1800) -> str:
    # Arguments travel over stdin so import tokens are absent from the process command line.
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-X", "utf8", "-c",
         "import json, sys, cli; sys.exit(cli.main(json.load(sys.stdin)))"],
        cwd=APPS / app, input=json.dumps(args), capture_output=True,
        encoding="utf-8", timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError(f"{app} CLI returned no result")
    return output[:output_limit]
