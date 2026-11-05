# -*- coding: utf-8 -*-
"""替换方案：先投新版，成功后再删旧稿（等价于替换）"""
import asyncio
import json
import sys
import urllib.request
import http.cookiejar

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\tools\biliapi")
from bilibili_api import Credential, video_uploader

CK = json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json", encoding="utf-8"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
OLD_AID = 117561643505239

VIDEO = r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\sample_10_replace.mp4"
COVER = r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\cover_01.jpg"
TITLE = "神人鉴定：你是哪种音游佬？千夏配音"
DESC = ("千夏声线配音，AI 合成，纯属整活。\n"
        "参考音色：オンゲキ 日向千夏（CV.岡咲美保）\n"
        "本视频音频与画面含 AI 生成内容。")
TAGS = ["音击", "神人", "蓝底", "配音", "日向千夏", "AI配音", "整活"]
TID = 138

cj = http.cookiejar.CookieJar()
for k, v in CK.items():
    cj.set_cookie(http.cookiejar.Cookie(0, k, v, None, False, ".bilibili.com", False, False, "/", True,
                                        False, None, False, None, None, {}))
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA), ("Referer", "https://member.bilibili.com/platform/upload-manager/article")]


def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(op.open(req, timeout=60).read().decode("utf-8"))


async def main():
    cred = Credential(sessdata=CK["SESSDATA"], bili_jct=CK["bili_jct"], dedeuserid=CK.get("DedeUserID"))
    meta = video_uploader.VideoMeta(tid=TID, title=TITLE, desc=DESC, cover=COVER, tags=TAGS, original=True)
    page = video_uploader.VideoUploaderPage(path=VIDEO, title=TITLE, description="")
    up = video_uploader.VideoUploader([page], meta, credential=cred)
    res = await up.start()
    print("upload result:", json.dumps(res, ensure_ascii=False)[:300], flush=True)
    new_bv = (res.get("data") or {}).get("bvid") or (res.get("data") or {}).get("aid")
    print("NEW:", new_bv, flush=True)
    return res


if __name__ == "__main__":
    asyncio.run(main())
