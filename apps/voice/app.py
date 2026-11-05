"""
千夏语音服务（自建云端推理）—— 最小可部署版

作用：把插件发来的 {text, speaker} 转成音频，返回给 QQ 插件。
本文件只做"协议适配 + 转发"，真正的推理交给 GPT-SoVITS 的 api_v2 服务
（或你自己换 CosyVoice，只要保留 /tts 返回音频字节这个形状）。

接口契约：
    POST /tts
      body: {"text": "...", "speaker": "qingxia", "format": "wav"}
      200 : audio/wav 字节
    GET /healthz -> {"ok": true, "backend": "..."}

部署：
    pip install -r requirements.txt
    # 先起 GPT-SoVITS 的 api_v2.py（默认 9880）
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

# ── 后端配置（用环境变量，别写死在代码里）──
GPT_SOVITS_URL = os.getenv("GPT_SOVITS_URL", "http://127.0.0.1:9880/tts")


def _prompt_text(env_text: str, ref_path: str) -> str:
    """参考文本优先取音频旁边的同名 .txt（UTF-8），避免环境变量/命令行传日文被转码弄坏。"""
    sidecar = os.path.splitext(ref_path)[0] + ".txt"
    if os.path.exists(sidecar):
        with open(sidecar, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        if text:
            return text
    return env_text


# 音色表：speaker id -> GPT-SoVITS 需要的参考音频与提示文本
#   ★ 这里的参考音频请用你有权使用的音源（自己录的、授权的、原创虚拟歌手）。
#     不要放未经许可的真人/声优音频。
_REF_QINGXIA = os.getenv("REF_AUDIO_QINGXIA", "/models/ref/qingxia.wav")
VOICE_MAP = {
    "qingxia": {
        "ref_audio_path": _REF_QINGXIA,
        "prompt_text": _prompt_text(os.getenv("REF_TEXT_QINGXIA", ""), _REF_QINGXIA),
        "prompt_lang": os.getenv("REF_LANG_QINGXIA", "zh"),
    },
}
# 别名：插件配置里写 chinatsu / hinata 也一样能路由到同一份参考音频
VOICE_MAP["chinatsu"] = dict(VOICE_MAP["qingxia"])
DEFAULT_SPEAKER = os.getenv("DEFAULT_SPEAKER", "qingxia")
REQUEST_TIMEOUT = float(os.getenv("TTS_TIMEOUT", "60"))

app = FastAPI(title="qianxia-voice", version="1.0.0")


class TTSRequest(BaseModel):
    text: str
    speaker: str | None = None
    format: Literal["wav", "mp3"] = "wav"


@app.get("/healthz")
def healthz():
    return {"ok": True, "backend": GPT_SOVITS_URL, "speakers": list(VOICE_MAP)}


@app.post("/tts")
async def tts(req: TTSRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    if len(text) > 200:
        raise HTTPException(status_code=400, detail="text too long")

    speaker = req.speaker or DEFAULT_SPEAKER
    voice = VOICE_MAP.get(speaker)
    if voice is None:
        raise HTTPException(status_code=400, detail=f"unknown speaker: {speaker}")
    if not os.path.exists(voice["ref_audio_path"]):
        raise HTTPException(status_code=500, detail="reference audio missing on server")

    payload = {
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": voice["ref_audio_path"],
        "prompt_text": voice["prompt_text"],
        "prompt_lang": voice["prompt_lang"],
        "media_type": "wav",
        "streaming_mode": False,
    }

    try:
        # trust_env=False：别让系统代理（Clash 等）把 127.0.0.1 的请求也劫持走，否则后端会 502
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, trust_env=False) as client:
            r = await client.post(GPT_SOVITS_URL, json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend unreachable: {exc}") from exc

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"backend error {r.status_code}")

    media = "audio/mpeg" if req.format == "mp3" else "audio/wav"
    return Response(content=r.content, media_type=media)
