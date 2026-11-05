import json, urllib.request, http.cookiejar
CK=json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json",encoding="utf-8"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
cj=http.cookiejar.CookieJar()
for k,v in CK.items():
    cj.set_cookie(http.cookiejar.Cookie(0,k,v,None,False,".bilibili.com",False,False,"/",True,False,None,False,None,None,{}))
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders=[("User-Agent",UA),("Referer","https://member.bilibili.com/platform/upload-manager/article")]
for ep,fmt in [("https://member.bilibili.com/x/web/archive/delete?aid=117561643505239&csrf=%s"%CK["bili_jct"],"post"),
               ("https://member.bilibili.com/x/vu/web/delete?aid=117561643505239&csrf=%s"%CK["bili_jct"],"post")]:
    try:
        req=urllib.request.Request(ep, data=b"", headers={"Content-Type":"application/json"})
        r=op.open(req,timeout=30).read().decode()
        print(ep.split('/x/')[1][:40],"->",r[:150])
    except Exception as e:
        print(ep.split('/x/')[1][:40],"ERR",str(e)[:60])
