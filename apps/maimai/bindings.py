"""QQ 身份 ↔ 查分器账号 的绑定，以及成绩的本地缓存。

存在 workspace/qq-memory/ 下（不进仓库、不随代码分发）：
    maimai-bindings.json   { "<openid>": {"qq": "...", "username": "...", "synced_at": 169...} }
    maimai-cache.json      { "<qq 或 username>": {"fetched_at": 169..., "data": {...b50...} } }

为什么要缓存：
    查成绩要打对方服务器，群里连着问几次就会被拖慢；b50 也不会秒变。
    默认 30 分钟内直接用缓存，`refresh=True` 强制重拉。
"""
from __future__ import annotations

import json
import os
import time

import maimai

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QQ_MEMORY = os.path.join(WS, "qq-memory")
BINDINGS = os.path.join(QQ_MEMORY, "maimai-bindings.json")
CACHE = os.path.join(QQ_MEMORY, "maimai-cache.json")

CACHE_TTL = 30 * 60  # 秒


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── 绑定 ──

def load_bindings(path: str = BINDINGS) -> dict:
    return _load(path)


def bind(openid: str, qq: str | None = None, username: str | None = None, path: str = BINDINGS) -> dict:
    if not openid:
        raise ValueError("openid 不能为空")
    if not qq and not username:
        raise ValueError("至少给 qq 或 username 一个")
    data = _load(path)
    rec = data.get(openid) or {}
    if qq:
        rec["qq"] = str(qq)
        rec.pop("username", None)
    if username:
        rec["username"] = str(username)
        rec.pop("qq", None)
    rec["synced_at"] = int(time.time())
    data[openid] = rec
    _save(path, data)
    return rec


def unbind(openid: str, path: str = BINDINGS) -> bool:
    data = _load(path)
    if openid not in data:
        return False
    del data[openid]
    _save(path, data)
    return True


def get_binding(openid: str, path: str = BINDINGS) -> dict | None:
    return _load(path).get(openid)


# ── 缓存 ──

def _cache_key(qq: str | None, username: str | None) -> str:
    return f"qq:{qq}" if qq else f"user:{username}"


def read_cache(qq: str | None = None, username: str | None = None,
               ttl: int = CACHE_TTL, path: str = CACHE) -> dict | None:
    entry = _load(path).get(_cache_key(qq, username))
    if not entry:
        return None
    if ttl > 0 and time.time() - entry.get("fetched_at", 0) > ttl:
        return None
    return entry.get("data")


def write_cache(data: dict, qq: str | None = None, username: str | None = None,
                path: str = CACHE) -> None:
    store = _load(path)
    store[_cache_key(qq, username)] = {"fetched_at": int(time.time()), "data": data}
    _save(path, store)


# ── 对外入口 ──

def fetch(openid: str | None = None, qq: str | None = None, username: str | None = None,
          refresh: bool = False, *, fallback_qq: str | None = None):
    """按 openid / qq / username 取成绩。返回 (data, source)。

    source: 'cache' | 'api' | None（失败时 data 是错误字典）
    """
    if not (qq or username) and openid:
        rec = get_binding(openid) or {}
        qq = rec.get("qq")
        username = rec.get("username")
    if not (qq or username):
        qq = fallback_qq
    if not (qq or username):
        return {"ok": False, "error": "没有绑定：先说「我是 <QQ号>」让我记住"}, None

    if not refresh:
        cached = read_cache(qq=qq, username=username)
        if cached:
            return cached, "cache"

    res = maimai.query_player(username=username, qq=qq)
    if not res.get("ok"):
        return res, None
    write_cache(res["data"], qq=qq, username=username)
    return res["data"], "api"
