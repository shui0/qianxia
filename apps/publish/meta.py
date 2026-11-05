import json, urllib.request, urllib.parse, io, sys
sys.stdout.reconfigure(encoding="utf-8")
hdr = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
       "Referer":"https://www.bilibili.com/"}
ids = ["117495021177437","112965240031867","460036846","116181113505139","840969110","961684302",
       "116001714799892","116264596932781","117460728551943","116154555173978"]
out=[]
for i in ids:
    q = "aid=" + i if i.isdigit() else "bvid=" + i
    u = "https://api.bilibili.com/x/web-interface/view?" + q
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=20))
        d = r.get("data") or {}
        out.append({"id": i, "bvid": d.get("bvid"), "title": d.get("title"), "dur": d.get("duration"),
                    "up": (d.get("owner") or {}).get("name"), "desc": (d.get("desc") or "")[:200]})
    except Exception as e:
        out.append({"id": i, "err": str(e)})
with io.open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish_meta.json","w",encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("ok")
