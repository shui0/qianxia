import asyncio
import base64
from pathlib import Path
import random

from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed, NetworkError
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel

from qianxia_runtime import APPS, command

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_BYTES = 5 * 1024 * 1024


class StickerConfig(BaseModel):
    qianxia_sticker_dir: Path = APPS.parent / "stickers"


__plugin_meta__ = PluginMetadata(
    name="千夏表情包", description="发送本地素材及斗图",
    usage="/表情包 [关键词]｜/斗图 [关键词]", config=StickerConfig, supported_adapters={"~onebot.v11"},
)
config = get_plugin_config(StickerConfig)
sticker = command("表情包")
fight = command("斗图")
active = set()


def images(root: Path, keyword: str) -> list[Path]:
    root = root.resolve()
    matches = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
            continue
        if not path.resolve().is_relative_to(root) or path.stat().st_size > MAX_BYTES:
            continue
        if keyword.casefold() in path.relative_to(root).as_posix().casefold():
            matches.append(path)
    return matches


async def image_segment(path: Path):
    content = await asyncio.to_thread(path.read_bytes)
    return MessageSegment.image("base64://" + base64.b64encode(content).decode("ascii"))


@sticker.handle()
async def handle_sticker(args: Message = CommandArg()):
    try:
        paths = await asyncio.to_thread(images, config.qianxia_sticker_dir, args.extract_plain_text().strip())
        if not paths:
            await sticker.finish("没找到这个词的表情包，换个词让我找找？")
        await sticker.finish(await image_segment(random.choice(paths)))
    except (OSError, ActionFailed, NetworkError):
        await sticker.finish("刚才的图没发出去。")


@fight.handle()
async def handle_fight(event: MessageEvent, args: Message = CommandArg()):
    scope = (event.self_id, event.group_id, 0) if isinstance(event, GroupMessageEvent) else (
        event.self_id, None, event.user_id,
    )
    if scope in active:
        await fight.finish("千夏正在发图，等等哦。")
    active.add(scope)
    try:
        paths = await asyncio.to_thread(images, config.qianxia_sticker_dir, args.extract_plain_text().strip())
        if not paths:
            await fight.finish("没找到这个词的表情包，换个词让我找找？")
        for index, path in enumerate(random.sample(paths, min(3, len(paths)))):
            if index:
                await asyncio.sleep(2.5)
            await fight.send(await image_segment(path))
    except (OSError, ActionFailed, NetworkError):
        await fight.finish("刚才的图没发出去。")
    finally:
        active.discard(scope)
