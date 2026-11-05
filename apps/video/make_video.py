#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
蓝底神人小视频生成器（千夏声线版）

用法:
    python make_video.py --script script_01.txt --out out/01.mp4

流程:
    文案逐行 -> GPT-SoVITS 适配层出语音 -> Pillow 画蓝底+头像+大字幕卡片
    -> ffmpeg 每句一段（带轻微推镜）-> 拼接成片

依赖: Pillow、ffmpeg（用 gptsovits 环境的 python 跑最省事）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FFMPEG = r"D:\cosmos\miniconda3\envs\gptsovits\Scripts\ffmpeg.exe"
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
]
FONT_REGULAR = [
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
]
BG = (26, 87, 200)          # 蓝底（纯色兜底）
BG_TOP = (77, 145, 216)     # 证件照蓝：上深
BG_BOTTOM = (198, 222, 250)  # 证件照蓝：下浅（参考同类视频封面的天空蓝渐变）
INK = (255, 255, 255)       # 字幕主色
STROKE = (12, 24, 48)       # 字幕描边
BG_IMAGE = r"C:\Users\baizh\.dsh\bot\workspace\assets\bg_ref.png"  # 从同类视频帧里取的同款背景


def gradient_bg(size: tuple[int, int], top=BG_TOP, bottom=BG_BOTTOM) -> Image.Image:
    W, H = size
    img = Image.new("RGB", (1, H))
    px = img.load()
    for y in range(H):
        t = y / max(H - 1, 1)
        px[0, y] = (int(top[0] + (bottom[0] - top[0]) * t),
                    int(top[1] + (bottom[1] - top[1]) * t),
                    int(top[2] + (bottom[2] - top[2]) * t))
    return img.resize((W, H))


def sky_bg(size: tuple[int, int], seed: int = 7) -> Image.Image:
    """证件照底图：天空蓝渐变 + 分形噪声云层（不是纯色，有起伏和纹理）"""
    import numpy as np
    from PIL import ImageFilter

    W, H = size
    rng = np.random.default_rng(seed)

    # 1. 竖向渐变底
    base = np.zeros((H, W, 3), dtype=np.float32)
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    for i in range(3):
        base[:, :, i] = BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t

    # 2. 分形噪声 -> 云
    noise = np.zeros((H, W), dtype=np.float32)
    amp, total = 1.0, 0.0
    for octave in range(5):
        cells = 4 * (2 ** octave)
        hh, ww = max(2, int(H / 1920 * cells * 2)), max(2, int(W / 1080 * cells * 2))
        small = rng.random((hh, ww)).astype(np.float32)
        layer = np.array(Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC),
                         dtype=np.float32) / 255.0
        noise += layer * amp
        total += amp
        amp *= 0.55
    noise /= total
    noise = (noise - noise.min()) / max(noise.max() - noise.min(), 1e-6)

    # 3. 云层：越靠下越白越淡，顶部留一点深
    clouds = np.clip((noise - 0.42) / 0.58, 0, 1) ** 1.4
    cloud_amt = clouds * (0.35 + 0.45 * t)          # 底部云更明显
    for i in range(3):
        base[:, :, i] = base[:, :, i] * (1 - cloud_amt) + 255 * cloud_amt

    # 4. 一点柔和光晕，别太死板
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    return img


def pick_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for f in (FONT_CANDIDATES if bold else FONT_REGULAR):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    raise SystemExit("找不到中文字体")


def tts(text: str, url: str, speaker: str, out_path: str) -> None:
    body = json.dumps({"text": text, "speaker": speaker, "format": "wav"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if not data.startswith(b"RIFF"):
        raise SystemExit(f"TTS 返回的不是 wav：{data[:80]!r}")
    with open(out_path, "wb") as fh:
        fh.write(data)


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _pop(sr: int, dur: float = 0.075, f0: float = 760.0, amp: float = 0.32):
    """合成一个短促的「咚」音效"""
    import numpy as np
    t = np.arange(int(sr * dur)) / sr
    env = np.exp(-t * 45) * (1 - np.exp(-t * 900))
    sig = np.sin(2 * np.pi * f0 * t) + 0.35 * np.sin(2 * np.pi * f0 * 2.02 * t)
    return (sig * env * amp).astype(np.float32)


def _swish(sr: int, dur: float = 0.22, amp: float = 0.16):
    """合成一个「唰」的噪声扫频"""
    import numpy as np
    n = int(sr * dur)
    t = np.arange(n) / sr
    noise = np.random.default_rng(3).normal(0, 1, n).astype(np.float32)
    # 简易高通：一阶差分
    noise = np.diff(noise, prepend=0.0)
    env = np.exp(-(t / dur) * 3.2) * (t / dur) ** 0.6
    return (noise * env * amp).astype(np.float32)


def build_audio(speech_wav: str, out_wav: str, head: float = 0.30, tail: float = 0.30) -> float:
    """给一句话加：开头鼓点 + 前奏留白 + 尾巴留白，返回总时长"""
    import numpy as np

    with wave.open(speech_wav, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        speech = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        speech = speech.reshape(-1, ch).mean(axis=1)

    lead = np.zeros(int(sr * head), dtype=np.float32)
    pop = _pop(sr)
    lead[: len(pop)] += pop[: len(lead)]
    tail_arr = np.zeros(int(sr * tail), dtype=np.float32)
    sw = _swish(sr)
    tail_arr[: len(sw)] += sw

    out = np.concatenate([lead, speech, tail_arr])
    pcm = np.clip(out, -1, 1)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767).astype(np.int16).tobytes())
    return len(out) / sr


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if font.getlength(cur + ch) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    # 末行只剩一两个字太丑，从上一行末尾挪几个字过来
    if len(lines) >= 2 and 0 < len(lines[-1]) <= 2:
        while len(lines[-1]) < 4 and len(lines[-2]) > 3:
            lines[-1] = lines[-2][-1] + lines[-1]
            lines[-2] = lines[-2][:-1]
    return lines


def build_card(text: str, bust: Image.Image, size: tuple[int, int], path: str,
               title: str | None, index: str | None, style: str = "cert",
               visible: int | None = None) -> None:
    """style=cert：证件照构图——正脸居中、头大、肩部顶到画底；style=bust：原来的半身照"""
    W, H = size
    card = (Image.open(BG_IMAGE).convert("RGB").resize((W, H), Image.LANCZOS)
            if (style == "cert" and os.path.exists(BG_IMAGE)) else Image.new("RGB", (W, H), BG))
    d = ImageDraw.Draw(card)

    if style == "cert":
        # 原图特征点（712x1399 的立绘）：帽顶、下巴、脸中心 x
        HAT_TOP, CHIN, FACE_X = 40, 470, 400
        scale = (H * 0.58) / (CHIN - HAT_TOP)
        big = bust.resize((int(bust.width * scale), int(bust.height * scale)), Image.LANCZOS)
        x = int(W / 2 - FACE_X * scale)
        y = int(H * 0.015 - HAT_TOP * scale)
        card.paste(big, (x, y), big)
    else:
        b = bust.copy()
        target_w = int(W * 0.94)
        if b.width != target_w:
            b = b.resize((target_w, int(b.height * target_w / b.width)), Image.LANCZOS)
        if b.height > int(H * 0.62):
            s = (H * 0.62) / b.height
            b = b.resize((int(b.width * s), int(b.height * s)), Image.LANCZOS)
        fade = 150
        alpha = b.split()[3]
        grad = Image.new("L", (1, b.height), 255)
        for yy in range(b.height - fade, b.height):
            grad.putpixel((0, yy), int(255 * (b.height - yy) / fade))
        alpha = Image.composite(alpha, Image.new("L", alpha.size, 0), grad.resize(alpha.size))
        b.putalpha(alpha)
        card.paste(b, ((W - b.width) // 2, int(H * 0.02)), b)

    # 底部极轻压暗（主要靠字幕自身的柔光，别把底图压脏）
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    g0, g1 = int(H * 0.72), H
    for yy in range(g0, g1):
        a = int(45 * (yy - g0) / (g1 - g0))
        sd.line([(0, yy), (W, yy)], fill=(8, 24, 52, a))
    card = Image.alpha_composite(card.convert("RGBA"), shade).convert("RGB")

    # 左上角小标（默认不画，给了才画）
    if title:
        f = pick_font(int(W * 0.042))
        ImageDraw.Draw(card).text((W * 0.05, H * 0.035), title, font=f, fill=(230, 240, 255))

    # 底部字幕：白字 + 柔和黑边（同款发光字幕，细字）
    # 注意：底部留出平台安全区（抖音/快手底部有 UI，文字别贴死）
    max_w = int(W * 0.90)
    box_bottom = int(H * 0.885)
    for size_px in (int(W * 0.082), int(W * 0.074), int(W * 0.066), int(W * 0.058)):
        font = pick_font(size_px, bold=False)
        lines = wrap(text, font, max_w)
        if len(lines) <= 3:
            break
    line_h = int(size_px * 1.38)
    total = line_h * len(lines)
    y0 = box_bottom - total

    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    yy = y0
    for ln in lines:
        w = font.getlength(ln)
        md.text(((W - w) / 2, yy), ln, font=font, fill=255)
        yy += line_h
    mask = mask.filter(ImageFilter.GaussianBlur(max(6, size_px // 6)))
    mask = mask.point(lambda v: min(255, int(v * 1.35)))
    card = Image.composite(Image.new("RGB", (W, H), (6, 18, 38)), card, mask)

    # 逐字出现：只画出前 visible 个字，行位置不动
    shown = []
    if visible is None:
        shown = list(lines)
    else:
        rem = max(0, int(visible))
        for ln in lines:
            if rem <= 0:
                shown.append("")
            elif rem >= len(ln):
                shown.append(ln)
                rem -= len(ln)
            else:
                shown.append(ln[:rem])
                rem = 0

    d = ImageDraw.Draw(card)
    yy = y0
    for ln, part in zip(lines, shown):
        full_w = font.getlength(ln)
        x_left = (W - full_w) / 2
        if part:
            d.text((x_left, yy), part, font=font, fill=(255, 255, 255),
                   stroke_width=max(2, size_px // 26), stroke_fill=(24, 40, 66))
        yy += line_h

    if index:
        f = pick_font(int(W * 0.05))
        d.text((W * 0.95, H * 0.035), index, font=f, fill=(255, 255, 255), anchor="ra")

    card.save(path)


def make_segment(frames, wav: str, dur: float, out: str, size: tuple[int, int], fps: int, zoom: bool) -> None:
    W, H = size
    vf = f"scale={W}:{H}"
    if zoom:
        step = 0.05 / max(dur * fps, 1)
        vf += (f",zoompan=z='min(1+{step:.6f}*on,1.06)':x='iw/2-(iw/zoom/2)'"
               f":y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")

    if isinstance(frames, str):
        frames = [(frames, dur)]

    if len(frames) == 1:
        src = ["-loop", "1", "-framerate", str(fps), "-i", frames[0][0]]
    else:
        listing = os.path.join(os.path.dirname(frames[0][0]), f"seq_{os.path.basename(frames[0][0])}.txt")
        with open(listing, "w", encoding="utf-8") as fh:
            for p, d in frames:
                fh.write(f"file '{p.replace(chr(92), '/')}'\n")
                fh.write(f"duration {d:.3f}\n")
            fh.write(f"file '{frames[-1][0].replace(chr(92), '/')}'\n")
        src = ["-f", "concat", "-safe", "0", "-i", listing]

    cmd = [FFMPEG, "-y", "-v", "error", *src,
           "-i", wav,
           "-t", f"{dur:.3f}",
           "-vf", vf,
           "-af", "apad",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", str(fps),
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
           out]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--portrait", default=r"C:\Users\baizh\.dsh\bot\workspace\assets\chinatsu_raw.webp")
    ap.add_argument("--style", default="cert", choices=["cert", "bust"], help="cert=证件照构图（默认），bust=半身照")
    ap.add_argument("--tts-url", default="http://127.0.0.1:8000/tts")
    ap.add_argument("--speaker", default="qingxia")
    ap.add_argument("--size", default="1080x1350")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--zoom", action="store_true", default=False)
    ap.add_argument("--no-zoom", dest="zoom", action="store_false")
    ap.add_argument("--title", default="", help="左上角小标，留空则不画")
    ap.add_argument("--index", action="store_true", default=False, help="右上角显示 序号/总数")
    ap.add_argument("--gap", type=float, default=0.32, help="每句尾巴留白秒数")
    ap.add_argument("--typing", action="store_true", default=True, help="字幕逐字出现")
    ap.add_argument("--no-typing", dest="typing", action="store_false")
    args = ap.parse_args()

    W, H = (int(x) for x in args.size.lower().split("x"))
    lines = [ln.strip() for ln in open(args.script, encoding="utf-8") if ln.strip()]
    if not lines:
        raise SystemExit("文案是空的")

    bust = Image.open(args.portrait).convert("RGBA")
    tmp = tempfile.mkdtemp(prefix="lanxi_")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    segs = []
    for i, text in enumerate(lines, 1):
        raw_wav = os.path.join(tmp, f"r{i:02d}.wav")
        wav = os.path.join(tmp, f"l{i:02d}.wav")
        tts(text, args.tts_url, args.speaker, raw_wav)
        speech_dur = wav_duration(raw_wav)
        head, tail = 0.30, 0.32
        dur = build_audio(raw_wav, wav, head=head, tail=tail)

        # 字幕按字逐个出现，时间按「标点权重大」估算
        frames = []
        if args.typing:
            w = [3 if c in "。！？…" else 2 if c in "，、；：—" else 1 for c in text]
            tw = sum(w) or 1
            marks = [0.30, 0.58, 0.82, 1.0]
            times, ids = [], []
            for frac in marks:
                target = frac * tw
                acc, idx = 0, len(text)
                for j, wt in enumerate(w):
                    acc += wt
                    if acc >= target:
                        idx = j + 1
                        break
                ids.append(idx)
                times.append(head + frac * speech_dur)
            times[0] = head
            pngs = []
            for k, vis in enumerate(ids):
                p = os.path.join(tmp, f"c{i:02d}_{k}.png")
                build_card(text, bust, (W, H), p, args.title or None,
                           (f"{i:02d}/{len(lines):02d}" if args.index else None),
                           args.style, visible=(None if vis >= len(text) else vis))
                pngs.append(p)
            for k in range(len(pngs) - 1):
                frames.append((pngs[k], max(0.08, times[k + 1] - times[k])))
            frames.append((pngs[-1], max(0.3, dur - times[-1])))
        else:
            p = os.path.join(tmp, f"c{i:02d}.png")
            build_card(text, bust, (W, H), p, args.title or None,
                       (f"{i:02d}/{len(lines):02d}" if args.index else None), args.style)
            frames = p

        seg = os.path.join(tmp, f"s{i:02d}.mp4")
        make_segment(frames, wav, dur, seg, (W, H), args.fps, args.zoom)
        segs.append(seg)
        print(f"[{i}/{len(lines)}] {dur:5.2f}s  {text}", flush=True)

    listing = os.path.join(tmp, "list.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        for s in segs:
            fh.write(f"file '{s.replace(chr(92), '/')}'\n")
    raw = os.path.join(tmp, "concat.mp4")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", listing, "-c", "copy", raw], check=True)

    # 响度标准化到 -14 LUFS（短视频平台常见标准），视频流拷贝不重编码
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", raw,
                    "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "1", args.out], check=True)
    print("OK ->", args.out, flush=True)


if __name__ == "__main__":
    main()







