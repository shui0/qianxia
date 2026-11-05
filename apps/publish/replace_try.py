# -*- coding: utf-8 -*-
"""把已发布稿件的视频文件替换成新渲染的版本（不新建稿件）"""
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\tools\biliapi")
from bilibili_api import Credential, video_uploader

BVID = "BV1nsxZ6aEom"
NEW_VIDEO = r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\sample_10_replace.mp4"
COOKIES = r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"


def bili_get(url, cookie_str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://member.bilibili.com/",
                                               "Cookie": cookie_str})
    return json.load(urllib.request.urlopen(req, timeout=25))


async def main():
    ck = json.load(open(COOKIES, encoding="utf-8"))
    cookie_str = "; ".join(f"{k}={v}" for k, v in ck.items())

    info = bili_get(f"https://api.bilibili.com/x/web-interface/view?bvid={BVID}", cookie_str)
    d = info["data"]
    aid = d["aid"]
    print("aid:", aid, "| title:", d["title"], "| cover:", d["pic"][:60], flush=True)

    cred = Credential(sessdata=ck["SESSDATA"], bili_jct=ck["bili_jct"],
                      dedeuserid=ck.get("DedeUserID"))

    title = d["title"]
    page = video_uploader.VideoUploaderPage(path=NEW_VIDEO, title=title, description="")
    meta = video_uploader.VideoMeta(tid=d["tid"], title=title, desc="", cover=r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\cover_01.jpg",
                                    tags=d.get("tname", ""), original=True)
    up = video_uploader.VideoUploader([page], meta, credential=cred)

    from bilibili_api.video_uploader import _choose_line
    up.line = await _choose_line(None)
    print("uploading...", flush=True)
    filename = await up._upload_page(page)
    print("upos filename:", filename, flush=True)

    body = {
        "aid": aid,
        "copyright": d.get("copyright", 1),
        "title": title,
        "cover": d["pic"],
        "tid": d["tid"],
        "tag": "",
        "desc": d.get("desc", ""),
        "videos": [{"filename": filename, "title": title, "desc": ""}],
        "no_reprint": 0,
        "open_elec": 1,
    }
    import http.cookiejar

    cj = http.cookiejar.CookieJar()
    for k, v in ck.items():
        cj.set_cookie(http.cookiejar.Cookie(0, k, v, None, False, ".bilibili.com",
                                            False, False, "/", True, False, None, False, None, None, {}))
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA),
                     ("Referer", "https://member.bilibili.com/platform/upload-manager/article")]

    url = f"https://member.bilibili.com/x/vu/web/edit?csrf={ck['bili_jct']}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(op.open(req, timeout=60).read().decode("utf-8"))
        print("edit resp:", json.dumps(r, ensure_ascii=False)[:400], flush=True)
    except Exception as e:
        body_txt = getattr(e, "read", lambda: b"")()
        print("edit ERR", type(e).__name__, str(e)[:100], body_txt[:300], flush=True)


if __name__ == "__main__":
    asyncio.run(main())



