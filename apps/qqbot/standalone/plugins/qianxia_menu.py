import re

from nonebot import on_message, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.plugin import PluginMetadata

from qianxia_runtime import allowed, command, group_config

require("qianxia_chat")
from plugins.qianxia_chat import conversation_key, message_text
from qianxia_vision import has_images

TEXT = (
    "千夏会这些，照着发就行～\n"
    "聊天｜群里 @千夏，或以“千夏，……”开头就能叫我；私聊直接发。\n"
    "看图｜群里 @我或以“千夏”开头，并带图片或引用图片问我；私聊直接发图也行，每次最多3张。\n"
    "联网｜/搜索 关键词；日服新曲每天更新，近期消息实时查证，回答会附来源。\n"
    "舞萌｜/舞萌 搜曲 曲名、/舞萌 谱面 曲名、/舞萌 评分 13.8 100.5。"
    "发 /舞萌 B50 查自己的 B50 成绩图，后面加 QQ 号可以查别人。/舞萌 推分 只在私聊用，需要先录入水鱼导入令牌。\n"
    "语音｜/语音 你好，让千夏念给你听。\n"
    "找图｜/搜图 日向千夏 5；也可以 @我说“来5张日向千夏”，AI会调用搜图。每次1到5张，发预览、画师和原作链接，随机选图并避开本会话最近20张。\n"
    "B 站｜/B站 搜索 关键词、/B站 详情 BV号、/B站 评论 BV号。\n"
    "小游戏｜/骰子 2d6、/猜数字 开局后直接发数字、/抽一个 随机抽群成员。\n"
    "表情包｜/表情包 舞萌 发一张，/斗图 舞萌 连发几张。\n"
    "记忆｜/好感度、/心情、/日记 查看、/日记 写。启用了群消息记录的群可以用 /周报。\n"
    "想再看一次，发 help 或 /菜单。"
)
HELP_REQUEST = re.compile(
    r"(?:千夏[，,、:\s]*)?(?:请问\s*)?"
    r"(?:菜单|功能|帮助|help(?:\s+me)?|指令|用法|使用说明|"
    r"(?:你)?(?:都)?(?:有(?:什么|哪些)功能|(?:能做|会)(?:什么|哪些功能)|(?:要)?怎么用))"
    r"[呀啊呢吗吧嘛\s]*[?？!！。]*"
)
__plugin_meta__ = PluginMetadata(
    name="千夏菜单", description="显示独立版指令", usage="/菜单", supported_adapters={"~onebot.v11"},
)
menu = command("菜单", aliases={"功能", "帮助"})


def wants_menu(event: MessageEvent) -> bool:
    if not allowed(event):
        return False
    text = message_text(event).casefold()
    return HELP_REQUEST.fullmatch(text) is not None or (
        not text and not has_images(event) and isinstance(event, GroupMessageEvent)
        and conversation_key(event, group_config().qianxia_groups) is not None
    )


plain_menu = on_message(rule=wants_menu, priority=15, block=True)


@menu.handle()
async def show_menu():
    await menu.finish(TEXT)


@plain_menu.handle()
async def show_plain_menu():
    await plain_menu.finish(TEXT)
