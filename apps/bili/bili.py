"""逛 B 站：搜索、看视频、读评论、发评论。

只用到 bilibili_api（在 tools/biliapi 里，调用时需要 PYTHONPATH）。
读操作匿名即可；发评论必须带登录态（apps/publish/cookies.json）。

    python cli.py search 桥姬
    python cli.py info BV1xx411c7mD
    python cli.py comments BV1xx411c7mD
    python cli.py post BV1xx411c7mD "说一句" --yes
"""
from __future__ import annotations

import asyncio
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COOKIES = os.path.join(WS, "apps", "publish", "cookies.json")

from bilibili_api import Credential, comment, search, video  # noqa: E402


def load_credential() -> Credential | None:
    if not os.path.exists(COOKIES):
        return None
    with open(COOKIES, encoding="utf-8") as fh:
        c = json.load(fh)
    if not c.get("SESSDATA"):
        return None
    return Credential(
        sessdata=c.get("SESSDATA"),
        bili_jct=c.get("bili_jct", ""),
        buvid3=c.get("buvid3", ""),
        dedeuserid=c.get("DedeUserID", ""),
    )


def _fmt_num(n) -> str:
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _fmt_time(sec) -> str:
    try:
        sec = int(sec)
    except Exception:
        return str(sec)
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def search_videos(keyword: str, page: int = 1, limit: int = 5) -> list[dict]:
    res = await search.search_by_type(
        keyword, search_type=search.SearchObjectType.VIDEO, page=page,
    )
    out = []
    for item in (res.get("result") or [])[:limit]:
        title = (item.get("title") or "").replace('<em class="keyword">', "").replace("</em>", "")
        out.append({
            "title": title,
            "author": item.get("author"),
            "bvid": item.get("bvid"),
            "play": item.get("play"),
            "duration": item.get("duration"),
            "pubdate": item.get("pubdate"),
        })
    return out


async def video_info(bvid: str) -> dict:
    v = video.Video(bvid=bvid)
    info = await v.get_info()
    st = info.get("stat") or {}
    return {
        "title": info.get("title"),
        "owner": (info.get("owner") or {}).get("name"),
        "bvid": info.get("bvid"),
        "aid": info.get("aid"),
        "desc": (info.get("desc") or "").strip(),
        "duration": info.get("duration"),
        "view": st.get("view"),
        "like": st.get("like"),
        "reply": st.get("reply"),
        "danmaku": st.get("danmaku"),
        "pubdate": info.get("pubdate"),
    }


async def top_comments(bvid: str, limit: int = 5) -> list[dict]:
    info = await video_info(bvid)
    res = await comment.get_comments(
        oid=info["aid"],
        type_=comment.CommentResourceType.VIDEO,
        page_index=1,
        order=comment.OrderType.LIKE,
    )
    out = []
    for item in (res.get("replies") or [])[:limit]:
        out.append({
            "user": (item.get("member") or {}).get("uname"),
            "like": item.get("like"),
            "text": (item.get("content") or {}).get("message", ""),
        })
    return out


async def send_comment(bvid: str, text: str) -> dict:
    cred = load_credential()
    if not cred:
        return {"ok": False, "error": "没有登录态（apps/publish/cookies.json）"}
    info = await video_info(bvid)
    try:
        res = await comment.send_comment(
            text=text,
            oid=info["aid"],
            type_=comment.CommentResourceType.VIDEO,
            credential=cred,
        )
    except Exception as e:  # 风控、频繁、内容违规都会抛
        return {"ok": False, "error": str(e)[:200]}
    rpid = ((res or {}).get("reply") or {}).get("rpid") or (res or {}).get("rpid")
    return {"ok": True, "rpid": rpid}


async def whoami() -> dict:
    from bilibili_api import user
    cred = load_credential()
    if not cred:
        return {"ok": False, "error": "没有登录态"}
    try:
        me = await user.get_self_info(cred)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True, "name": me.get("name"), "mid": me.get("mid"), "level": me.get("level")}
