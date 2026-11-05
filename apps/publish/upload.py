# -*- coding: utf-8 -*-
"""投稿到 B 站：bilibili-api-python 的 video_uploader"""
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\tools\biliapi")
from bilibili_api import Credential, video_uploader

COOKIES = r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json"
VIDEO = r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\sample_07_final.mp4"
TITLE = "神人鉴定：你是哪种音游佬？千夏配音"
DESC = ("千夏声线配音，AI 合成，纯属整活。\n"
        "参考音色：オンゲキ 日向千夏（CV.岡咲美保）\n"
        "本视频音频与画面含 AI 生成内容。")
TAGS = ["音击", "神人", "蓝底", "配音", "日向千夏", "AI配音", "整活"]
TID = 138  # 生活 -> 搞笑


def buvid3():
    req = urllib.request.Request("https://api.bilibili.com/x/frontend/finger/spi",
                                 headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    return d["data"]["b_3"]


async def main():
    ck = json.load(open(COOKIES, encoding="utf-8"))
    cred = Credential(sessdata=ck["SESSDATA"], bili_jct=ck["bili_jct"],
                      dedeuserid=ck.get("DedeUserID"), buvid3=buvid3())
    meta = video_uploader.VideoMeta(
        tid=TID, title=TITLE, desc=DESC, cover=r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\cover_01.jpg", tags=TAGS, original=True,
    )
    page = video_uploader.VideoUploaderPage(path=VIDEO, title=TITLE, description="")
    up = video_uploader.VideoUploader([page], meta, credential=cred)

    up.add_event_listener("START", lambda d: print("[start]", d.get("video"), flush=True))
    up.add_event_listener("PRE_UPLOAD", lambda d: print("[pre]", d.get("info", {}).get("ok"), flush=True))
    up.add_event_listener("AFTER_CHUNK", lambda d: print(f"[chunk] {d.get('chunk')}", flush=True))
    up.add_event_listener("COMPLETED", lambda d: print("[completed]", d, flush=True))

    await up.start()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

