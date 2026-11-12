import asyncio
from contextlib import suppress
from datetime import datetime
import json
import os

import httpx
from nonebot import get_driver, get_plugin_config, logger
from nonebot.plugin import PluginMetadata

from qianxia_jp import Catalog, SGT, next_refresh
from qianxia_web import SearchConfig

__plugin_meta__ = PluginMetadata(
    name='日服曲库每日刷新', description='每天后台刷新 SEGA 官方日服曲目目录',
    usage='自动更新，不发送群消息', supported_adapters={'~onebot.v11'},
)
config = get_plugin_config(SearchConfig)
catalog = Catalog(config.qianxia_maimai_jp_cache)
driver = get_driver()
task: asyncio.Task | None = None


async def refresh_once():
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=True,
                                     proxy=config.qianxia_search_proxy or None) as client:
            count = await catalog.refresh(client)
        logger.info(f'日服官方曲库已刷新，共 {count} 条')
    except (httpx.HTTPError, ValueError, OSError) as exc:
        logger.warning(f'日服官方曲库刷新失败，保留已有数据（{type(exc).__name__}）')


async def daily_refresh():
    if catalog.stale():
        await refresh_once()
    while True:
        now = datetime.now(SGT)
        target = next_refresh(now, config.qianxia_maimai_jp_refresh_hour)
        try:
            status = config.qianxia_maimai_jp_cache.with_suffix('.schedule.json')
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text(json.dumps({'pid': os.getpid(), 'next_refresh': target.isoformat(),
                                          'enabled': True}, ensure_ascii=False), encoding='utf8')
        except OSError as exc:
            logger.warning(f'写入日服曲库刷新状态失败（{type(exc).__name__}）')
        await asyncio.sleep((target - now).total_seconds())
        await refresh_once()


@driver.on_startup
async def start_refresh():
    global task
    if config.qianxia_maimai_jp_refresh_enabled:
        task = asyncio.create_task(daily_refresh())


@driver.on_shutdown
async def stop_refresh():
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
