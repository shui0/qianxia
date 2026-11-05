"""舞萌 DX 曲库与评分的核心逻辑（无第三方依赖，纯标准库）。

数据来自查分器公开接口（diving-fish），缓存到 data/music_data.json。
这里只做「查」和「算」，不碰账号、不联网（除了 update_data.py 刷新数据）。

用法：
    from maimai import load, search, format_song, chart_rating

    songs = load()
    hit = search(songs, "Grievous")[0]
    print(format_song(hit))
    print(chart_rating(13.8, 100.5))   # -> 309
"""
from __future__ import annotations

import json
import math
import os
import difflib
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "music_data.json")

DIFF_NAMES = ["BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER"]

# 达成率 → rating 系数（maimai DX）。顺序从高到低，取第一个满足的档。
COEF_TABLE = [
    (100.5, 0.224),
    (100.0, 0.216),
    (99.5, 0.211),
    (99.0, 0.208),
    (98.0, 0.203),
    (97.0, 0.200),
    (94.0, 0.168),
    (90.0, 0.152),
    (80.0, 0.136),
    (75.0, 0.120),
    (70.0, 0.104),
    (60.0, 0.096),
    (50.0, 0.088),
    (0.0, 0.080),
]


@dataclass
class Chart:
    name: str
    level: str
    ds: float
    notes: int | None
    charter: str


def load(path: str = DATA) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def coefficient(achievement: float) -> float:
    """成就率 → 系数。achievement 用百分数，如 100.5。"""
    for threshold, coef in COEF_TABLE:
        if achievement >= threshold:
            return coef
    return COEF_TABLE[-1][1]


def chart_rating(ds: float, achievement: float) -> int:
    """单谱面 rating = floor(定数 × 系数 × 100)。"""
    return math.floor(ds * coefficient(achievement) * 100)


def charts(song: dict) -> list[Chart]:
    out = []
    ds_list = song.get("ds") or []
    lv_list = song.get("level") or []
    chart_list = song.get("charts") or []
    for i, ds in enumerate(ds_list):
        c = chart_list[i] if i < len(chart_list) else {}
        notes = c.get("notes")
        out.append(Chart(
            name=DIFF_NAMES[i] if i < len(DIFF_NAMES) else f"DIFF{i}",
            level=str(lv_list[i]) if i < len(lv_list) else "?",
            ds=float(ds),
            notes=(sum(notes) if isinstance(notes, list) and notes else None),
            charter=c.get("charter") or "-",
        ))
    return out


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if not ch.isspace())


def search(songs: list[dict], query: str, limit: int = 5) -> list[dict]:
    """先精确/子串，再模糊。返回按匹配度排序的歌曲列表。"""
    q = _norm(query)
    if not q:
        return []
    exact, prefix, contains = [], [], []
    titles = []
    for s in songs:
        t = _norm(s.get("title", ""))
        titles.append((s, t))
        if t == q:
            exact.append(s)
        elif t.startswith(q):
            prefix.append(s)
        elif q in t:
            contains.append(s)
    if exact or prefix or contains:
        return (exact + prefix + contains)[:limit]

    # 模糊：按相似度取前几名，低于阈值的不返回
    scored = []
    for s, t in titles:
        r = difflib.SequenceMatcher(None, q, t).ratio()
        if r >= 0.6:
            scored.append((r, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]


def format_song(song: dict, with_notes: bool = False) -> str:
    """给 QQ 群看的紧凑格式。"""
    info = song.get("basic_info") or {}
    head = f"{song.get('title')}  [{song.get('type')}]"
    meta = []
    if info.get("artist"):
        meta.append(info["artist"])
    if info.get("bpm"):
        meta.append(f"BPM {info['bpm']}")
    if info.get("genre"):
        meta.append(info["genre"])
    lines = [head]
    if meta:
        lines.append(" · ".join(str(m) for m in meta))
    for c in charts(song):
        tail = f"{c.name}  {c.level}（{c.ds:g}）"
        if with_notes and c.notes:
            tail += f"  {c.notes} notes · {c.charter}"
        lines.append("  " + tail)
    return "\n".join(lines)


def format_rating(ds: float, achievement: float) -> str:
    coef = coefficient(achievement)
    r = chart_rating(ds, achievement)
    return f"定数 {ds:g} × {achievement:g}% → 系数 {coef:.3f} → **{r}**"
