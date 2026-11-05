"""全成绩（b50 之外）的获取与缓存。

公开接口 `query/player` 只给 best 50；要看全部记录必须用本人「导入令牌」
（查分器 → 设置 → 导入令牌 / Import-Token），走 `/player/records`。

令牌是敏感凭据，只存在 workspace/qq-memory/maimai-bindings.json，不进仓库。
"""
from __future__ import annotations

import json
import os
import time

import bindings
import maimai

CACHE = os.path.join(bindings.QQ_MEMORY, "maimai-records-cache.json")
CACHE_TTL = 6 * 3600  # 全成绩变化慢，6 小时够


def _load(path: str = CACHE) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _save(data: dict, path: str = CACHE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def set_token(openid: str, token: str, path: str = bindings.BINDINGS) -> dict:
    data = bindings.load_bindings(path)
    rec = data.get(openid) or {}
    rec["token"] = token.strip()
    rec["token_at"] = int(time.time())
    data[openid] = rec
    bindings._save(path, data)
    return rec


def has_token(openid: str) -> bool:
    rec = bindings.get_binding(openid) or {}
    return bool(rec.get("token"))


def fetch_records(openid: str, refresh: bool = False) -> tuple[dict, str | None]:
    """返回 (records 列表 或 错误字典, 来源 'cache'/'api'/None)。"""
    rec = bindings.get_binding(openid) or {}
    token = rec.get("token")
    if not token:
        return {"ok": False, "error": "没有导入令牌"}, None

    if not refresh:
        entry = _load().get(openid)
        if entry and time.time() - entry.get("fetched_at", 0) <= CACHE_TTL:
            return entry.get("records") or [], "cache"

    res = maimai.query_records(token)
    if not res.get("ok"):
        return res, None
    records = res["data"]
    store = _load()
    store[openid] = {"fetched_at": int(time.time()), "records": records}
    _save(store)
    return records, "api"


def analyze(openid: str, top: int = 5, refresh: bool = False):
    records, source = fetch_records(openid, refresh=refresh)
    if isinstance(records, dict):  # 错误
        return records, None
    return maimai.analyze_records(records, top=top), source
