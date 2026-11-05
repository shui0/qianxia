# -*- coding: utf-8 -*-
"""替换已发布稿件视频：用 web/edit 接口，body 基于原稿件字段构造"""
import json
import sys
import urllib.request
import http.cookiejar

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\tools\biliapi")

CK = json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json", encoding="utf-8"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
AID = 117561643505239

cj = http.cookiejar.CookieJar()
for k, v in CK.items():
    cj.set_cookie(http.cookiejar.Cookie(0, k, v, None, False, ".bilibili.com", False, False, "/", True,
                                        False, None, False, None, None, {}))
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA), ("Referer", "https://member.bilibili.com/platform/upload-manager/article")]


def get(u):
    return json.loads(op.open(u, timeout=30).read().decode("utf-8"))


lst = get("https://member.bilibili.com/x/web/archives?status=is_pubing,pubed,not_pubed,reject&pn=1&ps=20")
item = None
for a in (lst.get("data") or {}).get("arc_audits") or []:
    ar = a.get("Archive") or {}
    if ar.get("aid") == AID:
        item = ar
        break
print("archive found:", bool(item))
if not item:
    sys.exit(1)
print(json.dumps(item, ensure_ascii=False)[:800])

filename = sys.argv[1] if len(sys.argv) > 1 else None
if not filename:
    print("need filename")
    sys.exit(1)

body = dict(item)
body["videos"] = [{"filename": filename, "title": item.get("title", ""), "desc": ""}]
body["csrf"] = CK["bili_jct"]
for k in ("state", "state_desc", "ctime", "ptime", "is_union_video", "is_only_self"):
    body.pop(k, None)

u = f"https://member.bilibili.com/x/vu/web/edit?csrf={CK['bili_jct']}"
req = urllib.request.Request(u, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
try:
    r = json.loads(op.open(req, timeout=60).read().decode("utf-8"))
    print("edit resp:", json.dumps(r, ensure_ascii=False)[:400])
except Exception as e:
    txt = getattr(e, "read", lambda: b"")()
    print("ERR", str(e)[:80], txt[:300])
