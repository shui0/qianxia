import random
import re

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed, NetworkError
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from qianxia_runtime import allowed, command, memory_store

__plugin_meta__ = PluginMetadata(
    name="千夏小游戏", description="骰子、猜数字和群内抽人",
    usage="/骰子 2d6｜/猜数字 [数字/结束]｜/抽一个", supported_adapters={"~onebot.v11"},
)
dice = command("骰子", aliases={"掷骰子"})
guess = command("猜数字")
draw = command("抽一个")


def roll_dice(expression: str, randint=random.randint):
    parsed = re.fullmatch(r"([0-9]{0,2})d([0-9]{1,4})([+-][0-9]{1,4})?", expression.lower())
    if not parsed:
        raise ValueError("用法：/骰子 2d6 或 /骰子 3d8+2")
    count, sides, offset = int(parsed[1] or 1), int(parsed[2]), int(parsed[3] or 0)
    if not 1 <= count <= 20 or not 2 <= sides <= 1000:
        raise ValueError("骰子数量为 1 到 20，面数为 2 到 1000。")
    rolls = [randint(1, sides) for _ in range(count)]
    return rolls, sum(rolls) + offset


@dice.handle()
async def handle_dice(args: Message = CommandArg()):
    try:
        rolls, total = roll_dice(args.extract_plain_text().strip() or "d6")
    except ValueError as exc:
        await dice.finish(str(exc))
    await dice.finish(f"千夏掷出 {'、'.join(map(str, rolls))}，合计 {total}。")


def game_key(event: MessageEvent):
    return (event.self_id, event.group_id, 0) if isinstance(event, GroupMessageEvent) else (
        event.self_id, None, event.user_id,
    )


def guess_result(event: MessageEvent, text: str) -> str:
    if not re.fullmatch(r"[0-9]{1,3}", text) or not 1 <= int(text) <= 100:
        return "猜一个 1 到 100 的整数。"
    outcome, tries, target = memory_store().guess(game_key(event), int(text))
    return {
        "missing": "还没开局，先发 /猜数字。",
        "high": "大了！",
        "low": "小了！",
        "win": f"猜中了！你用了 {tries} 次。",
        "gaveup": f"20 次用完啦，答案是 {target}。",
    }[outcome]


@guess.handle()
async def handle_guess(event: MessageEvent, args: Message = CommandArg()):
    value = args.extract_plain_text().strip()
    store = memory_store()
    key = game_key(event)
    if not value:
        started = store.start_guess(key, random.randint(1, 100))
        await guess.finish("千夏想好了一个 1 到 100 的整数，直接发数字来猜！" if started else "这局还没猜完呢，接着来吧！")
    if value == "结束":
        target = store.end_guess(key)
        await guess.finish(f"这局结束，答案是 {target}。" if target is not None else "还没开局。")
    await guess.finish(guess_result(event, value))


def active_guess(event: MessageEvent) -> bool:
    text = event.get_plaintext().strip()
    return (allowed(event) and bool(re.fullmatch(r"[0-9]{1,3}", text))
            and memory_store().has_guess(game_key(event)))


quick_guess = on_message(rule=active_guess, priority=15, block=True)


@quick_guess.handle()
async def handle_number(event: MessageEvent):
    await quick_guess.finish(guess_result(event, event.get_plaintext().strip()))


@draw.handle()
async def handle_draw(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await draw.finish("到群里叫我抽吧，这里只有我们两个呀。")
    try:
        members = await bot.get_group_member_list(group_id=event.group_id)
    except (ActionFailed, NetworkError):
        await draw.finish("这次没拿到群成员名单，还抽不了。")
    candidates = sorted({int(row["user_id"]) for row in members} - {event.self_id})
    if not candidates:
        await draw.finish("名单里没找到能抽的人呢。")
    await draw.finish(MessageSegment.text("千夏抽到的是 ") + MessageSegment.at(random.choice(candidates)))
