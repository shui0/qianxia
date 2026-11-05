import json, urllib.request, http.cookiejar
ck=json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json",encoding="utf-8"))
cj=http.cookiejar.CookieJar()
for k,v in ck.items(): cj.set_cookie(http.cookiejar.Cookie(0,k,v,None,False,".bilibili.com",False,False,"/",True,False,None,False,None,None,{}))
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders=[("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36"),("Referer","https://member.bilibili.com/")]
for u in ["https://member.bilibili.com/x/web/archives?status=is_pubing,pubed,not_pubed&pn=1&ps=10",
          "https://api.bilibili.com/x/web-interface/nav"]:
    try:
        d=json.loads(op.open(u,timeout=25).read().decode("utf-8"))
        if "archives" in u:
            print("code", d.get("code"), "msg", d.get("message"))
            for a in (d.get("data",{}).get("arc_audits") or [])[:5]:
                ar=a.get("Archive") or {}
                print("  ", ar.get("bvid"), "|", ar.get("state_desc") or ar.get("state"), "|", ar.get("title"))
        else:
            print("nav code", d.get("code"), "uname", (d.get("data") or {}).get("uname"), "mid", (d.get("data") or {}).get("mid"))
    except Exception as e:
        print("ERR", u[:40], type(e).__name__, str(e)[:80])
