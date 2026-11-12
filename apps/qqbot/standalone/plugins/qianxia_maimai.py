import asyncio
import base64
import json
import math
import subprocess

from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from qianxia_b50 import load_b50_covers, render_b50
from qianxia_runtime import command, run_cli

HELP = ("想查舞萌的话，照着这些发就行：/舞萌 搜曲 曲名、/舞萌 谱面 曲名、/舞萌 评分 13.8 100.5、"
        "/舞萌 曲库、/舞萌 B50 [QQ号或查分器用户名] 出成绩图、/舞萌 绑定 用户名、/舞萌 推分。"
        "导入令牌请在私聊使用 /舞萌 令牌 你的导入令牌。")

__plugin_meta__ = PluginMetadata(
    name="舞萌 DX", description="曲库、Rating、成绩绑定和推分",
    usage=HELP, supported_adapters={"~onebot.v11"},
)

matcher = command("舞萌", aliases={"maimai"})
cli_lock = asyncio.Lock()


def command_args(text: str, identity: str, *, private: bool, sender_qq: int | None = None) -> list[str]:
    parts = text.split(maxsplit=1)
    action = parts[0].lower() if parts else ""
    value = parts[1].strip() if len(parts) == 2 else ""
    if action == "曲库" and not value:
        return ["count"]
    if action == "搜曲" and value:
        return ["search", "--", value]
    if action == "谱面" and value:
        return ["song", "--notes", "--", value]
    if action == "评分":
        try:
            ds, ach = map(float, value.split())
        except ValueError:
            raise ValueError("用法：/舞萌 评分 13.8 100.5") from None
        if not (math.isfinite(ds) and math.isfinite(ach) and 0 < ds <= 20 and 0 <= ach <= 101):
            raise ValueError("定数或达成率好像填错啦，检查一下再发给我。")
        return ["rating", "--ds", str(ds), "--ach", str(ach)]
    if action == "b50":
        if value.isascii() and value.isdecimal():
            return ["player", "--json", "--qq", value]
        if value:
            return ["player", "--json", "--", value]
        args = ["player", "--json", "--openid", identity]
        if sender_qq is not None:
            args.extend(["--fallback-qq", str(sender_qq)])
        return args
    if action == "绑定" and value:
        if value.isascii() and value.isdecimal():
            return ["bind", "--openid", identity, "--qq", value]
        return ["bind", "--openid", identity, f"--username={value}"] if value.startswith("-") else [
            "bind", "--openid", identity, "--username", value,
        ]
    if action == "令牌" and value:
        if not private:
            raise ValueError("导入令牌要私聊给我，别往群里发哦。")
        if len(value) > 256 or any(char.isspace() for char in value):
            raise ValueError("这个令牌的格式好像不对，检查一下有没有多复制空格吧。")
        return ["bind", "--openid", identity, f"--token={value}"]
    if action == "推分" and not value:
        if not private:
            raise ValueError("推分建议到私聊找我看吧，得用到你的全量成绩。")
        return ["player", "--openid", identity, "--all"]
    raise ValueError(HELP)


async def run_maimai(args: list[str]) -> str:
    async with cli_lock:
        return await run_cli("maimai", args)


async def b50_reply(args: list[str]) -> MessageSegment:
    async with cli_lock:
        raw = await run_cli("maimai", args, output_limit=None)
    data = json.loads(raw)
    if data.get("ok") is False:
        return MessageSegment.text("这次没查到 B50，看看水鱼查分器有没有绑好 QQ、公开成绩吧。")
    covers = await load_b50_covers(data)
    image = await asyncio.to_thread(render_b50, data, covers)
    return MessageSegment.image("base64://" + base64.b64encode(image).decode("ascii"))


@matcher.handle()
async def handle_maimai(event: MessageEvent, args: Message = CommandArg()):
    identity = f"onebot:{event.self_id}:{event.user_id}"
    try:
        argv = command_args(args.extract_plain_text(), identity,
                            private=isinstance(event, PrivateMessageEvent), sender_qq=event.user_id)
        if argv[:2] == ["player", "--json"]:
            await matcher.finish(await b50_reply(argv))
        answer = "给你查到这些：\n" + await run_maimai(argv)
    except ValueError as exc:
        answer = str(exc)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        answer = "这次舞萌没查成，过会儿再试试吧。"
    await matcher.finish(MessageSegment.text(answer))
