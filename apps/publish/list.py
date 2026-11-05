import json, urllib.request, http.cookiejar
CK=json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json",encoding="utf-8"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
cj=http.cookiejar.CookieJar()
for k,v in CK.items():
    cj.set_cookie(http.cookiejar.Cookie(0,k,v,None,False,".bilibili.com",False,False,"/",True,False,None,False,None,None,{}))
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders=[("User-Agent",UA),("Referer","https://member.bilibili.com/")]
d=json.loads(op.open("https://member.bilibili.com/x/web/archives?status=is_pubing,pubed,not_pubed,reject&pn=1&ps=10",timeout=25).read().decode())
for a in (d.get("data") or {}).get("arc_audits") or []:
    ar=a.get("Archive") or {}
    print(ar.get("bvid"), "|", ar.get("state_desc") or ar.get("state"), "|", ar.get("duration"), "s |", ar.get("title"))
