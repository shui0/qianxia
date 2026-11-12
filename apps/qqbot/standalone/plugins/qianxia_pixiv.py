import base64
import asyncio
import hashlib
import re

from nonebot import get_plugin_config, logger, on_message, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.matcher import current_matcher
from nonebot.plugin import PluginMetadata

from qianxia_pixiv import Pixiv, PixivConfig, PixivError, ImageRequest, MAX_IMAGES
from qianxia_pixiv_recent import RecentImages
from qianxia_runtime import allowed, command, group_config

require('qianxia_chat')
from plugins.qianxia_chat import conversation_key, message_text, chat

__plugin_meta__ = PluginMetadata(name='千夏找图', description='搜索 Pixiv 公开插画并发送预览与原作链接',
    usage='/搜图 关键词 [1-5]，或 @千夏 找张星空的图', config=PixivConfig,
    supported_adapters={'~onebot.v11'})
config = get_plugin_config(PixivConfig)
pixiv = Pixiv(config)
recent = RecentImages(group_config().qianxia_memory_path)
locks = [asyncio.Lock() for _ in range(32)]
matcher = command('搜图', aliases={'找图', 'pixiv', 'Pixiv', 'P站', 'p站'})


Query = ImageRequest


def command_query(text: str) -> Query:
    text = text.strip()
    match = re.fullmatch(r'(.+?)\s+(\d{1,2})', text)
    query = Query(match[1], int(match[2])) if match else Query(text)
    if not 1 <= len(query.keyword) <= 80 or not 1 <= query.count <= MAX_IMAGES:
        raise ValueError('想看什么图？发 /搜图 关键词 就行，后面加 1 到 5 可以选张数。')
    return query


def parse_request(text: str) -> Query | None:
    text = text.strip()
    if text.startswith('/'):
        return None
    explicit = re.fullmatch(r'(?:搜图|找图|pixiv|P站)\s+(.+)', text, re.I)
    if explicit:
        try:
            return command_query(explicit[1])
        except ValueError:
            return None
    text = re.sub(r'^(?:千夏[，,\s]*)?(?:(?:请|麻烦你|帮我|给我|替我|帮忙|能不能|可以)\s*){0,4}', '', text)
    text = re.sub(r'^(?:在|从)?(?:pixiv|P站)(?:上)?\s*', '', text, flags=re.I)
    match = re.fullmatch(
        r'(?:搜索?|找|来|发)([一两二三四五1-5])?(?:张|幅)?(?:下|个)?\s*'
        r'(?:(?:pixiv|P站)(?:上)?的?)?\s*(.+?)(?:的)?(?:图片|插画|壁纸|图)'
        r'(?:看看|吧|呀|哦|呗)?[!！。?？]*', text, re.I)
    if not match or not 1 <= len(match[2]) <= 80:
        return None
    return Query(match[2], {'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'1':1,'2':2,'3':3,'4':4,'5':5}.get(match[1], 1))


def wants_image(event: MessageEvent) -> bool:
    return (config.qianxia_pixiv_enabled and allowed(event)
            and (not isinstance(event, GroupMessageEvent)
                 or conversation_key(event, group_config().qianxia_groups) is not None)
            and parse_request(message_text(event)) is not None)


natural = on_message(rule=wants_image, priority=20, block=True)


def image_scope(event: MessageEvent) -> tuple[int, int, int]:
    return ((event.self_id, event.group_id, 0) if isinstance(event, GroupMessageEvent)
            else (event.self_id, 0, event.user_id))


def conversation_scope(event: MessageEvent):
    return event.self_id, event.group_id if isinstance(event,GroupMessageEvent) else None, event.user_id


async def reply_images(query: Query, send, *, key: tuple[int, int, int]):
    async with locks[hash(key) % len(locks)]:
        return await _reply_images(query, send, key)


async def _reply_images(query: Query, send, key: tuple[int, int, int]):
    if not config.qianxia_pixiv_enabled:
        await send('我这边还没开搜图，暂时找不了哦。')
        return 0
    excluded = recent.ids(key)
    delivered = 0
    images_sent = 0
    for _ in range(3):
        try:
            works = await pixiv.search(query.keyword, query.count - delivered, exclude_ids=excluded)
        except PixivError as exc:
            logger.warning(f'Pixiv 搜图失败（{type(exc).__name__}）')
            if not delivered:
                await send('这次 P 站没连上，过会儿再让我找找吧。')
            return images_sent
        if not works:
            break
        for work in works:
            if work.id in excluded:
                continue
            excluded.add(work.id)
            caption = f'给你找来啦：{work.title}\n画师：{work.author}\n原作：{work.url}'
            message = Message(MessageSegment.text(caption))
            digest = None
            try:
                data = await pixiv.image(work.image_url)
                digest = hashlib.sha256(data).hexdigest()
                if recent.has_hash(key, digest):
                    continue
                message += MessageSegment.image('base64://' + base64.b64encode(data).decode('ascii'))
            except PixivError:
                message += MessageSegment.text('\n这张预览没发出来，先点原作链接看吧。')
            await send(message)
            if digest:
                recent.mark(key, work.id, digest)
                images_sent += 1
            delivered += 1
            if delivered == query.count:
                return images_sent
    if not delivered:
        await send('这次没找到新的合适图片，换个关键词让我再找找？')
    return images_sent


@matcher.handle()
async def handle_command(event: MessageEvent, args: Message = CommandArg()):
    try:
        query = command_query(args.extract_plain_text())
    except ValueError as exc:
        await matcher.finish(str(exc))
    await chat.reply(conversation_scope(event),event.get_plaintext(),matcher.send,
                     allow_web=False,image_request=query)


@natural.handle()
async def handle_natural(event: MessageEvent):
    query = parse_request(message_text(event))
    if query:
        await chat.reply(conversation_scope(event),event.get_plaintext(),natural.send,
                         allow_web=False,image_request=query)


async def send_ai_images(key, query: ImageRequest) -> int:
    bot_id, group, user = key
    scope = (bot_id,group,0) if group is not None else (bot_id,0,user)
    return await reply_images(query,current_matcher.get().send,key=scope)


chat.image_handler = send_ai_images
chat.image_ai_enabled = config.qianxia_pixiv_enabled and config.qianxia_pixiv_ai_enabled
