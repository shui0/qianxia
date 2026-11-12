import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from ipaddress import ip_address
import json
from pathlib import Path
import random
import sqlite3
import re
import time
from typing import Any

import httpx
from nonebot import get_plugin_config, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment, PrivateMessageEvent
from nonebot.adapters.onebot.v11.exception import ActionFailed, NetworkError
from nonebot.plugin import PluginMetadata
from nonebot.message import event_preprocessor
from pydantic import Field
from qianxia_runtime import memory_store
from qianxia_state import Memory, affinity_label, mood_label
from qianxia_persona import CONNECT_FAILURE, VOICE, fact_lines, valid_rephrase, short_fallback
from qianxia_search_trace import trace
from qianxia_pixiv import IMAGE_TOOL, ImageRequest
from qianxia_vision import (
    FOLLOWUP, VISION_NOTE, Vision, VisionConfig, VisualInput, has_images, text_content, visual_content,
)
from qianxia_web import (
    Search, SearchConfig, SearchError, EmptySearch, TOOL, FAILURE, UNKNOWN,
    sourced_reply, evidence, instructions, reading_instructions, quote_instructions,
    recover_quotes, needs_lookup, unverified,
)

DOCS = Path(__file__).resolve().parents[4] / "docs"
ConversationKey = tuple[int, int | None, int]
Turn = dict[str, Any]


class Config(SearchConfig, VisionConfig):
    qianxia_model_base_url: str = "https://api.deepseek.com/v1"
    qianxia_model: str = "deepseek-chat"
    qianxia_model_api_key: str = ""
    qianxia_groups: set[int] = Field(default_factory=set)
    qianxia_proactive_enabled: bool = True
    qianxia_proactive_groups: set[int] = Field(default_factory=set)
    qianxia_proactive_keywords: list[str] = Field(default_factory=lambda: [
        "舞萌", "maimai", "音击", "オンゲキ", "ongeki", "时代剧", "爬树", "野外探险",
    ])
    qianxia_proactive_probability: float = Field(.05, ge=0, le=1)
    qianxia_proactive_cooldown: int = Field(180, ge=30)
    qianxia_proactive_delay: int = Field(25, ge=1, le=120)
    qianxia_direct_prompt: Path = DOCS / "prompt19-direct.txt"
    qianxia_group_prompt: Path = DOCS / "prompt19-group.txt"


__plugin_meta__ = PluginMetadata(
    name="千夏对话",
    description="在私聊、群聊 @ 或句首千夏唤醒时以千夏人设回复",
    usage="私聊直接发送；群聊 @ 千夏或以“千夏，……”开头",
    config=Config,
    supported_adapters={"~onebot.v11"},
)


WAKEUP = re.compile(r'^千夏[\s，,：:、！!？?。～~]*')


def wakeup_text(text: str) -> str | None:
    text = text.strip()
    match = WAKEUP.match(text)
    return text[match.end():].strip() if match else None


def message_text(event) -> str:
    text = event.get_plaintext().strip()
    addressed = wakeup_text(text) if isinstance(event, GroupMessageEvent) else None
    # A bare name is still a real conversational call, rather than an empty @.
    return addressed if addressed else text


def conversation_key(event, groups: set[int]) -> ConversationKey | None:
    if not isinstance(event, (PrivateMessageEvent, GroupMessageEvent)):
        return None
    if event.user_id == event.self_id:
        return None
    if isinstance(event, GroupMessageEvent):
        if groups and event.group_id not in groups:
            return None
        # 适配器会移除部分 @ 段，原始消息仍保留实际发送的段。
        mentioned = any(segment.type == "at" and str(segment.data.get("qq")) == str(event.self_id)
                        for segment in event.original_message)
        if not mentioned and wakeup_text(event.get_plaintext()) is None:
            return None
        return event.self_id, event.group_id, event.user_id
    return event.self_id, None, event.user_id


class Chat:
    def __init__(self, config: Config, memory: Memory | None = None):
        self.config = config
        self.memory = memory
        self.web = Search(config)
        self.vision = Vision(config)
        self.last_pictures: OrderedDict[ConversationKey, tuple[float, list[str]]] = OrderedDict()
        self.image_handler: Callable[[ConversationKey, ImageRequest], Awaitable[int]] | None = None
        self.image_ai_enabled = True
        self.prompts = {
            False: config.qianxia_direct_prompt.read_text(encoding="utf-8-sig"),
            True: config.qianxia_group_prompt.read_text(encoding="utf-8-sig"),
        }
        self.history: OrderedDict[ConversationKey, list[Turn]] = OrderedDict()
        self.locks = [asyncio.Lock() for _ in range(32)]

    async def reply(
        self, key: ConversationKey, text: str, send: Callable[[str], Awaitable[None]],
        *, allow_web: bool = True, forced_query: str | None = None,
        image_request: ImageRequest | None = None,
        pictures: list[str] | None = None, picture_note: str = '',
        load_pictures: Callable[[], Awaitable[VisualInput]] | None = None,
    ) -> None:
        async with self.locks[hash(key) % len(self.locks)]:
            if load_pictures is not None:
                # Serialize download and reply together: an immediate followup
                # must wait for this image instead of reading the previous one.
                self.last_pictures.pop(key, None)
                visual = await load_pictures()
                pictures, picture_note = visual.images, visual.note
            clock = time.monotonic()
            for old_key, (stamp, _) in list(self.last_pictures.items()):
                if clock - stamp >= 600:
                    self.last_pictures.pop(old_key, None)
            if pictures is not None:
                self.last_pictures.pop(key, None)
            if pictures is not None and not pictures:
                await send(picture_note or '这张图片没读到，重新发一下给我看看吧。')
                return
            current_pictures = pictures or []
            if (pictures is None and self.config.qianxia_vision_enabled and allow_web
                    and forced_query is None and image_request is None and FOLLOWUP.search(text)):
                current_pictures = self.last_pictures.get(key, (0, []))[1]
            saved_text = text or '看看这张图片。'
            if current_pictures:
                saved_text += f'\n[附图{len(current_pictures)}张]'
            persona = self.prompts[key[1] is not None]
            user_turn = {"role": "user", "content": saved_text}
            history = self.history.get(key)
            now = time.time()
            if self.memory:
                try:
                    if history is None:
                        history = self.memory.history(key)
                    score, energy, mood = self.memory.profile(key, now)
                    persona += f"\n和对方的关系：{affinity_label(score)}。千夏现在：{mood_label(energy, mood)}。"
                except sqlite3.Error as exc:
                    logger.warning(f"读取千夏记忆失败（{type(exc).__name__}）")
            history = history or []
            if current_pictures:
                persona += VISION_NOTE
                # Keep room for visual tokens in the local 4096-token context.
                history = [{**turn, 'content': text_content(turn.get('content'))[:300]}
                           for turn in history[-4:]]
            model_turn = ({'role': 'user', 'content': visual_content(saved_text, current_pictures)}
                          if current_pictures else user_turn)
            prompt = {"role": "system", "content": persona}
            answer = image_request or await self.complete([prompt, *history, model_turn], use_web=allow_web,
                                         forced_query=forced_query,
                                         allow_images=allow_web and forced_query is None)
            if isinstance(answer, ImageRequest):
                if self.image_handler is None:
                    answer = '搜图这边还没连上，等会儿再叫我试试吧。'
                    await send(answer)
                else:
                    sent = await self.image_handler(key, answer)
                    answer = f'搜图“{answer.keyword}”，本轮实际发送了 {sent} 张图片。'
            else:
                if picture_note:
                    answer = picture_note + '\n' + answer
                await send(answer)
            if pictures:
                self.last_pictures[key] = (clock, pictures)
                self.last_pictures.move_to_end(key)
                while len(self.last_pictures) > 32:
                    self.last_pictures.popitem(last=False)
            if self.memory:
                try:
                    self.memory.save_turn(key, saved_text, answer, now)
                except sqlite3.Error as exc:
                    logger.warning(f"写入千夏记忆失败（{type(exc).__name__}）")
            self.history[key] = [*history, user_turn, {"role": "assistant", "content": answer}][-12:]
            self.history.move_to_end(key)
            if len(self.history) > 256:
                self.history.popitem(last=False)

    async def complete(self, messages: list[Turn], *, use_web: bool = False,
                       forced_query: str | None = None, allow_images: bool = False) -> str | ImageRequest:
        url = httpx.URL(self.config.qianxia_model_base_url.rstrip("/") + "/chat/completions")
        try:
            loopback = ip_address(url.host).is_loopback
        except ValueError:
            loopback = url.host.rstrip(".").lower() == "localhost"
        headers = {}
        if self.config.qianxia_model_api_key:
            headers["Authorization"] = f"Bearer {self.config.qianxia_model_api_key}"
        working = [dict(turn) for turn in messages]
        latest_user = next((turn for turn in reversed(messages) if turn.get('role') == 'user'), {})
        user_content = latest_user.get('content', '')
        has_pictures = isinstance(user_content, list) and any(
            isinstance(part, dict) and part.get('type') == 'image_url' for part in user_content)
        enabled = use_web and self.config.qianxia_search_enabled
        images_enabled = allow_images and self.image_ai_enabled and self.image_handler is not None and forced_query is None
        available_tools = ([TOOL] if enabled else []) + ([IMAGE_TOOL] if images_enabled else [])
        if forced_query is not None and not enabled:
            return '我这边还没开联网搜索，暂时查不了这个。'
        if enabled:
            if working and working[0]['role'] == 'system':
                working[0]['content'] += instructions()
            else:
                working.insert(0, {'role': 'system', 'content': instructions()})
        question = text_content(user_content)
        if images_enabled and re.search(r'(?:不要|别|不需要|不用)(?:真的|实际|现在|立刻)?(?:发|搜|找)(?:图|图片)|先别发',question):
            images_enabled = False
            available_tools = [TOOL] if enabled else []
        if images_enabled:
            tool_note = ('\n你可以调用 search_images 搜索并实际发送图片。用户说“来5张某角色”等省略图片二字的请求也能理解。'
                         '从本轮话和近期上下文确认角色及张数，未说数量时为1，每轮最多5张。'
                         '明确要求看图就实际调用工具，不要只口头答应或编造图片链接。'
                         '用户仅问有没有功能、引用别人的话、讨论假设、明确说不要发图时，不调用。')
            if working and working[0]['role'] == 'system':
                working[0]['content'] += tool_note
            else:
                working.insert(0,{'role':'system','content':tool_note})
        if enabled and not has_pictures and forced_query is None and not (images_enabled and re.search(r'张|幅|图|壁纸|picture|image',question,re.I)):
            forced_query = self.web.required_query(question)
        sources = []
        async with httpx.AsyncClient(timeout=90 if has_pictures else 30, trust_env=not loopback) as client:
            async def request(turns, tools=False, grounded=False):
                body = {'model': self.config.qianxia_model, 'messages': turns}
                if has_pictures:
                    body['max_tokens'] = 400
                if tools:
                    body.update(tools=available_tools, tool_choice='auto', max_tokens=512)
                elif grounded:
                    body['max_tokens'] = 512
                    body['temperature'] = 0
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                return response.json()['choices'][0]['message']

            if forced_query is not None:
                calls = [{'id': 'forced-web-search', 'type': 'function', 'function': {
                    'name': 'web_search', 'arguments': json.dumps({'query': forced_query})}}]
                message = {'role': 'assistant', 'content': None, 'tool_calls': calls}
            else:
                selection = working
                if images_enabled and len(working) > 6:
                    selection = [working[0], *[{**turn,'content':text_content(turn.get('content',''))[:450]}
                                 for turn in working[1:-1][-4:]], working[-1]]
                message = await request(selection, tools=bool(available_tools))
                calls = message.get('tool_calls') if available_tools else None
                if enabled and not has_pictures and not calls and needs_lookup(message.get('content') or '', question):
                    # Discard the uncertain draft; it is neither sent nor used as evidence.
                    calls = [{'id': 'uncertainty-web-search', 'type': 'function', 'function': {
                        'name': 'web_search', 'arguments': json.dumps({'query': question.strip()[:160]})}}]
                    message = {'role': 'assistant', 'content': None, 'tool_calls': calls}
            if calls:
                first = calls[0].get('function',{}) if isinstance(calls,list) and isinstance(calls[0],dict) else {}
                if images_enabled and isinstance(first,dict) and first.get('name') == 'search_images':
                    try:
                        return ImageRequest.from_tool(first.get('arguments','{}'))
                    except (ValueError,TypeError):
                        return '关键词和张数没对上，一轮可以找1到5张，告诉我想看谁就好。'
                for index, call in enumerate(calls):
                    function = call.get('function', {})
                    if index > 0 or function.get('name') != 'web_search':
                        continue
                    else:
                        try:
                            arguments = json.loads(function.get('arguments', '{}'))
                            query = arguments.get('query')
                            sources = await self.web.search(query)
                            trace('search', question, count=len(sources), urls=[r.url for r in sources])
                            sources = await self.web.read(question or query, sources)
                            trace('read', question, kinds=[r.content_kind for r in sources], lengths=[len(r.snippet) for r in sources])
                        except EmptySearch:
                            return UNKNOWN
                        except (SearchError, ValueError, AttributeError, TypeError) as exc:
                            logger.warning(f'千夏联网搜索失败（{type(exc).__name__}）')
                            return FAILURE
                if not sources:
                    return UNKNOWN
                # A compact shared character voice keeps replies natural while
                # current evidence stays isolated from old answers in history.
                reader_text = json.dumps({
                        'question': question[:1200], 'retrieval': json.loads(evidence(query, sources)),
                    }, ensure_ascii=False)
                reader_content = (visual_content(reader_text, [p['image_url']['url'] for p in user_content
                                  if p.get('type') == 'image_url']) if has_pictures else reader_text)
                message = await request([
                    {'role': 'system', 'content': reading_instructions() + (VISION_NOTE + '图片也属于本轮证据。' if has_pictures else '')},
                    {'role': 'user', 'content': reader_content},
                ], grounded=True)
                draft = message.get('content')
                trace('reader', question, refused=not isinstance(draft, str) or unverified(draft, sources))
                if not has_pictures and isinstance(draft, str) and unverified(draft, sources):
                    try:
                        extracted = await request([
                            {'role': 'system', 'content': quote_instructions()},
                            {'role': 'user', 'content': json.dumps({
                                'question': question[:1200], 'retrieval': json.loads(evidence(query, sources)),
                            }, ensure_ascii=False)},
                        ], grounded=True)
                        recovered = recover_quotes(extracted.get('content'), sources)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                        recovered = None
                    trace('quote_recovery', question, accepted=bool(recovered))
                    if recovered:
                        draft = recovered
                        message = {'content': draft}
                if (self.config.qianxia_web_persona_enabled and isinstance(draft, str)
                        and not unverified(draft, sources)):
                    # Facts are already read. The voice pass sees no raw webpages,
                    # and its output must preserve the listed names and numbers.
                    try:
                        styled = await request([
                            {'role': 'system', 'content': VOICE +
                             '下面是已经核对过的答案，只把它改成千夏自然对朋友说的话，不重新回答或补知识。'
                             '保留所有正确条目、曲名、型号、数字、地区版本和来源编号。'
                             '删掉报告开场、免责声明、完整性讨论、排除项分析和操作建议；不要引入被排除的项目。'
                             '直接接话给答案，不重复整句问题，不写来源链接或来源列表，程序会附上。'},
                            {'role': 'user', 'content': json.dumps({'question': question[:300], 'draft': fact_lines(draft)}, ensure_ascii=False)},
                        ], grounded=True)
                        text = styled.get('content')
                        message = {'content': text if isinstance(text, str) and valid_rephrase(draft, text)
                                   else short_fallback(draft)}
                    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                        message = {'content': short_fallback(draft)}
        answer = message.get('content')
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("模型返回空文本")
        if sources and unverified(answer, sources):
            trace('final', question, outcome='unknown')
            return UNKNOWN
        if sources:
            trace('final', question, outcome='answer', length=len(answer))
        return sourced_reply(answer, sources) if sources else answer.strip()


config = get_plugin_config(Config)
chat = Chat(config, memory_store())
matcher = on_message(priority=99, block=False)
pending: dict[tuple[int, int], asyncio.Task] = {}
last_auto: dict[tuple[int, int], float] = {}


@event_preprocessor
async def cancel_pending_when_addressed(event: GroupMessageEvent | PrivateMessageEvent):
    # Runs before menu/Pixiv matchers too, so a direct call cannot leave an
    # older random reply queued behind the requested answer.
    if isinstance(event, GroupMessageEvent) and conversation_key(event, config.qianxia_groups) is not None:
        task = pending.pop((event.self_id, event.group_id), None)
        if task is not None:
            task.cancel()


async def send_text(text: str) -> None:
    await matcher.send(MessageSegment.text(text))


def proactive_allowed(event: GroupMessageEvent, text: str, settings: Config) -> bool:
    return (
        settings.qianxia_proactive_enabled
        and bool(text) and not text.startswith("/") and event.user_id != event.self_id
        and (not settings.qianxia_proactive_groups or event.group_id in settings.qianxia_proactive_groups)
        and (not settings.qianxia_groups or event.group_id in settings.qianxia_groups)
    )


def proactive_trigger(text: str, settings: Config) -> bool:
    normalized = text.casefold()
    for keyword in settings.qianxia_proactive_keywords:
        keyword = keyword.strip().casefold()
        if keyword and keyword in normalized:
            return True
    return random.random() < settings.qianxia_proactive_probability


async def proactive_reply(bot: Bot, key: ConversationKey, text: str) -> None:
    group = key[1]
    if group is None:
        return
    try:
        await asyncio.sleep(config.qianxia_proactive_delay)

        async def send(answer: str):
            await bot.send_group_msg(group_id=group, message=MessageSegment.text(answer))

        await chat.reply(key, text, send, allow_web=False)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError,
            ActionFailed, NetworkError) as exc:
        logger.warning(f"千夏主动接话失败（{type(exc).__name__}）")
    finally:
        scope = (key[0], group)
        if pending.get(scope) is asyncio.current_task():
            pending.pop(scope, None)


@matcher.handle()
async def handle_message(bot: Bot, event: PrivateMessageEvent | GroupMessageEvent):
    key = conversation_key(event, config.qianxia_groups)
    text = message_text(event)
    if event.get_plaintext().strip().startswith("/"):
        return
    if isinstance(event, GroupMessageEvent):
        scope = (event.self_id, event.group_id)
        if key is not None and scope in pending:
            pending.pop(scope).cancel()
        if key is None and proactive_allowed(event, text, config):
            now = time.monotonic()
            if (scope not in pending
                    and now - last_auto.get(scope, -float("inf")) >= config.qianxia_proactive_cooldown
                    and proactive_trigger(text, config)):
                last_auto[scope] = now
                pending[scope] = asyncio.create_task(proactive_reply(
                    bot, (event.self_id, event.group_id, event.user_id), text,
                ))
    if key is None:
        return
    try:
        picture_message = has_images(event)
        if not text and not picture_message:
            return
        await chat.reply(key, text, send_text,
                         load_pictures=(lambda: chat.vision.read(bot, event)) if picture_message else None)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(f"千夏模型请求失败（{type(exc).__name__}）")
        await send_text(CONNECT_FAILURE)
