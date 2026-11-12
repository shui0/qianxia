import httpx
from nonebot import logger, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from qianxia_runtime import command
from qianxia_persona import CONNECT_FAILURE

require('qianxia_chat')
from plugins.qianxia_chat import chat

__plugin_meta__ = PluginMetadata(
    name='千夏联网搜索', description='搜索公开网页并附上来源',
    usage='/搜索 关键词，也可以在聊天时直接要求千夏联网查资料', supported_adapters={'~onebot.v11'},
)
matcher = command('搜索', aliases={'联网'})


@matcher.handle()
async def search_web(event: MessageEvent, args: Message = CommandArg()):
    query = args.extract_plain_text().strip()
    if not 1 <= len(query) <= 160:
        await matcher.finish('想查什么？发 /搜索 关键词 就行，别超过 160 字哦。')
    group = event.group_id if isinstance(event, GroupMessageEvent) else None
    async def send(answer):
        await matcher.send(answer)
    try:
        await chat.reply((event.self_id, group, event.user_id), query, send, forced_query=query)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(f'千夏联网回答失败（{type(exc).__name__}）')
        await matcher.finish(CONNECT_FAILURE)
