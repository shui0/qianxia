"""舞萌 DX 曲库与评分的核心逻辑（无第三方依赖，纯标准库）。

数据来自查分器公开接口（diving-fish），缓存到 data/music_data.json。
别名表在 data/aliases.json：俗称/中文名 → 正式曲名，搜索时先过一遍。

谱面类型（type）在游戏里有三种，这里统一成短标签：
    SD  → ST（标准谱面）
    DX  → DX（DX 谱面）
    其它 → 宴（宴会场，公开数据源目前不含，见 README）

用法：
    from maimai import load, search, format_entries, chart_rating

    songs = load()
    hits = search(songs, "命嫌")          # 别名也能搜到
    print(format_entries(hits))           # ST/DX 分开展示
    print(chart_rating(13.8, 100.5))      # -> 309
"""
from __future__ import annotations

import json
import math
import os
import difflib
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "music_data.json")
ALIASES = os.path.join(HERE, "data", "aliases.json")
STATS = os.path.join(HERE, "data", "chart_stats.json")
PLAYER_API = "https://www.diving-fish.com/api/maimaidxprober/query/player"
UA = "qianxia-maimai/1.0"

DIFF_NAMES = ["BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER"]
TYPE_LABEL = {"SD": "ST", "DX": "DX", "UTAGE": "宴", "utage": "宴"}

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


def type_label(raw: str) -> str:
    return TYPE_LABEL.get(raw, "宴" if str(raw).lower().startswith("utage") else str(raw))


# ── 别名 ──

def load_aliases(path: str = ALIASES) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if not ch.isspace())


def resolve_alias(query: str, aliases: dict[str, str]) -> tuple[str, str | None]:
    """把俗称换成正式曲名。返回 (用于搜索的词, 命中的别名或 None)。"""
    q = _norm(query)
    if not q:
        return query, None
    for alias, title in aliases.items():
        if _norm(alias) == q:
            return title, alias
    return query, None


def save_alias(alias: str, title: str, path: str = ALIASES) -> None:
    raw = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    raw[alias] = title
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def delete_alias(alias: str, path: str = ALIASES) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if alias not in raw:
        return False
    del raw[alias]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    return True


# ── 评分 ──

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


# ── 搜索 ──

def search(songs: list[dict], query: str, limit: int = 5, aliases: dict[str, str] | None = None) -> list[dict]:
    """先过别名，再精确/子串，最后模糊。返回按匹配度排序的歌曲列表。"""
    if aliases is None:
        aliases = load_aliases()
    query, _ = resolve_alias(query, aliases)

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

    scored = []
    for s, t in titles:
        r = difflib.SequenceMatcher(None, q, t).ratio()
        if r >= 0.6:
            scored.append((r, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]


def same_title(songs: list[dict], title: str) -> list[dict]:
    """取同名的全部条目（ST 与 DX 是两条数据）。"""
    t = _norm(title)
    return [s for s in songs if _norm(s.get("title", "")) == t]


def format_song(song: dict, with_notes: bool = False, stats: dict | None = None) -> str:
    """单条谱面（ST 或 DX），给 QQ 群看的紧凑格式。"""
    info = song.get("basic_info") or {}
    tag = type_label(song.get("type", ""))
    lines = [f"【{tag}】{song.get('title')}"]
    meta = []
    if info.get("artist"):
        meta.append(info["artist"])
    if info.get("bpm"):
        meta.append(f"BPM {info['bpm']}")
    if meta:
        lines.append(" · ".join(str(m) for m in meta))
    for i, c in enumerate(charts(song)):
        tail = f"  {c.name}  {c.level}（{c.ds:g}）"
        if with_notes and c.notes:
            tail += f"  {c.notes} notes · {c.charter}"
        lines.append(tail)
        if stats is not None:
            st = chart_stats(song, i, stats)
            if st and st.get("fit") is not None:
                extra = f"      ↳ 拟合 {st['fit']:.2f}"
                if st.get("avg") is not None:
                    extra += f" · 平均 {st['avg']:.2f}%"
                if st.get("cnt"):
                    extra += f" · {int(st['cnt'])} 次"
                lines.append(extra)
    return "\n".join(lines)


def format_entries(entries: list[dict], with_notes: bool = False, with_stats: bool = True) -> str:
    """把同名条目（ST + DX）拼成一块，按 ST → DX → 宴 排序。"""
    order = {"ST": 0, "DX": 1, "宴": 2}
    entries = sorted(entries, key=lambda s: order.get(type_label(s.get("type", "")), 9))
    stats = load_stats() if with_stats else None
    return "\n\n".join(format_song(s, with_notes=with_notes, stats=stats) for s in entries)


def load_stats(path: str = STATS) -> dict:
    """谱面统计（拟合定数 / 平均达成率 / 游玩次数），来自查分器的 chart_stats。"""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("charts", raw)


def chart_stats(song: dict, index: int, stats: dict | None = None) -> dict | None:
    if stats is None:
        stats = load_stats()
    arr = stats.get(str(song.get("id", "")), [])
    if index < len(arr):
        s = arr[index]
        return {
            "fit": s.get("fit_diff"),
            "avg": s.get("avg"),
            "cnt": s.get("cnt"),
            "std": s.get("std_dev"),
        }
    return None


def query_player(username: str, b50: bool = True, timeout: int = 15) -> dict:
    """查群友成绩（查分器用户名）。不需要 token，但对方得先在查分器注册并公开。"""
    import urllib.error
    import urllib.request

    body = json.dumps({"username": username, "b50": bool(b50)}).encode("utf-8")
    req = urllib.request.Request(
        PLAYER_API, data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        try:
            msg = json.loads(detail).get("message", detail)
        except Exception:
            msg = detail
        return {"ok": False, "error": msg, "status": e.code}
    except Exception as e:  # 超时、DNS 等
        return {"ok": False, "error": str(e)}


def format_player(data: dict, top: int = 5) -> str:
    name = data.get("nickname") or data.get("username") or "?"
    rating = data.get("rating") or 0
    lines = [f"{name} · rating {rating}"]
    charts = data.get("charts") or {}
    rows = []
    for group in ("sd", "dx"):
        rows.extend(charts.get(group) or [])
    rows.sort(key=lambda c: -(c.get("ra") or 0))
    for c in rows[:top]:
        typ = "ST" if c.get("type") == "SD" else "DX"
        ach = c.get("achievements") or 0
        lines.append(
            f"  【{typ}】{c.get('title')}  {DIFF_NAMES[c.get('level_index', 0)]} "
            f"{c.get('ds')} · {ach:.4f}% → {c.get('ra')}"
        )
    return "\n".join(lines)


def format_rating(ds: float, achievement: float) -> str:
    coef = coefficient(achievement)
    r = chart_rating(ds, achievement)
    return f"定数 {ds:g} × {achievement:g}% → 系数 {coef:.3f} → **{r}**"
