import base64

import httpx
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel

from qianxia_runtime import command

MAX_AUDIO_BYTES = 8 * 1024 * 1024


class VoiceConfig(BaseModel):
    qianxia_tts_url: str = "http://127.0.0.1:8000/tts"
    qianxia_tts_speaker: str = "qingxia"
    qianxia_tts_token: str = ""


__plugin_meta__ = PluginMetadata(
    name="千夏语音", description="把文字合成为 QQ 语音",
    usage="/语音 要念的文字", config=VoiceConfig, supported_adapters={"~onebot.v11"},
)
config = get_plugin_config(VoiceConfig)
matcher = command("语音", aliases={"say"})


async def synthesize(text: str) -> bytes:
    if not 1 <= len(text) <= 200:
        raise ValueError("想让我念哪句？发 /语音 加上文字就行，最多 200 字哦。")
    headers = {"Authorization": f"Bearer {config.qianxia_tts_token}"} if config.qianxia_tts_token else {}
    async with httpx.AsyncClient(timeout=65, trust_env=False) as client:
        async with client.stream("POST", config.qianxia_tts_url, headers=headers, json={
            "text": text, "speaker": config.qianxia_tts_speaker, "format": "wav",
        }) as response:
            response.raise_for_status()
            if not response.headers.get("content-type", "").lower().startswith("audio/"):
                raise ValueError("这次没拿到能发的语音，我还念不了这句。")
            audio = bytearray()
            async for chunk in response.aiter_bytes():
                audio.extend(chunk)
                if len(audio) > MAX_AUDIO_BYTES:
                    raise ValueError("这段语音太大啦，把句子分短一点再让我念吧。")
    if not audio:
        raise ValueError("这次语音没生成出来，换句短一点的试试？")
    return bytes(audio)


@matcher.handle()
async def handle_voice(args: Message = CommandArg()):
    try:
        audio = await synthesize(args.extract_plain_text().strip())
    except ValueError as exc:
        await matcher.finish(MessageSegment.text(str(exc)))
    except (httpx.HTTPError, httpx.InvalidURL):
        await matcher.finish(MessageSegment.text("声音这边还没连上，等会儿再让我念吧。"))
    await matcher.finish(MessageSegment.record("base64://" + base64.b64encode(audio).decode("ascii")))
