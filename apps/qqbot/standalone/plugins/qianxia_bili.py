import ast
import re
import secrets
import subprocess
import time

from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel, Field

from qianxia_runtime import APPS, command, run_cli

HELP = "/B站 搜索 关键词｜/B站 详情 BV号｜/B站 评论 BV号"
VIDEO = re.compile(r"(?:https://www\.bilibili\.com/video/)?(BV[0-9A-Za-z]{10})(?:[/?#]\S*)?")


class BiliConfig(BaseModel):
    qianxia_bili_post_users: set[int] = Field(default_factory=set)


__plugin_meta__ = PluginMetadata(
    name="逛 B 站", description="搜索、视频详情、评论读取和确认发评",
    usage=HELP, config=BiliConfig, supported_adapters={"~onebot.v11"},
)
config = get_plugin_config(BiliConfig)
matcher = command("B站", aliases={"bili", "b站"})


def video_id(text: str) -> str:
    match = VIDEO.fullmatch(text)
    if not match:
        raise ValueError("把 BV 号或 B 站视频链接发给我吧。")
    return match[1]


def read_args(action: str, argument: str) -> list[str]:
    if action == "搜索" and 0 < len(argument) <= 100:
        return ["search", "--", argument]
    if action in ("详情", "评论"):
        return ["info" if action == "详情" else "comments", video_id(argument)]
    raise ValueError(HELP)


class CommentDrafts:
    def __init__(self):
        self.pending = {}

    def prepare(self, owner, bvid: str, text: str, now: float) -> str:
        self.pending = {key: draft for key, draft in self.pending.items() if draft[0] > now}
        code = secrets.token_hex(3)
        self.pending[owner] = (now + 120, code, bvid, text)
        return code

    def consume(self, owner, code: str, now: float) -> tuple[str, str] | None:
        draft = self.pending.get(owner)
        if draft is None or draft[0] <= now or draft[1] != code:
            return None
        del self.pending[owner]
        return draft[2], draft[3]


drafts = CommentDrafts()


async def run_bili(action: str, argument: str, event: MessageEvent) -> str:
    if action not in ("发评论", "确认"):
        return "给你找到了：\n" + await run_cli("bili", read_args(action, argument))
    if not isinstance(event, PrivateMessageEvent) or event.user_id not in config.qianxia_bili_post_users:
        return "发评论这件事得让已经配置好的操作者私聊找我哦。"
    if not (APPS / "publish/cookies.json").is_file():
        return "我这边 B 站还没登录，暂时发不了评论。"
    owner = event.self_id, event.user_id
    now = time.monotonic()
    if action == "发评论":
        parts = argument.split(maxsplit=1)
        if len(parts) != 2 or len(parts[1]) > 300:
            raise ValueError("用法：/B站 发评论 BV号 评论内容（最多 300 字）")
        bvid, text = video_id(parts[0]), parts[1]
        code = drafts.prepare(owner, bvid, text, now)
        return f"准备在 {bvid} 发这条：\n{text}\n看好内容，两分钟内发 /B站 确认 {code} 我就发出去。"
    draft = drafts.consume(owner, argument, now)
    if draft is None:
        return "这个确认码对不上，可能已经过期啦。重新让我准备一条吧。"
    bvid, text = draft
    output = await run_cli("bili", ["post", "--yes", "--", bvid, text])
    try:
        result = ast.literal_eval(output)
    except (ValueError, SyntaxError):
        result = {}
    return "评论发出去啦。" if isinstance(result, dict) and result.get("ok") is True else "B 站没回成功，我还不能确定发出去了。"


@matcher.handle()
async def handle_bili(event: MessageEvent, args: Message = CommandArg()):
    parts = args.extract_plain_text().split(maxsplit=1)
    action = parts[0] if parts else ""
    argument = parts[1] if len(parts) == 2 else ""
    try:
        answer = await run_bili(action, argument.strip(), event)
    except ValueError as exc:
        answer = str(exc)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        answer = "这次 B 站没连上，过会儿再叫我试试吧。"
    await matcher.finish(MessageSegment.text(answer))
