import json, urllib.request, http.cookiejar
ck=json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json",encoding="utf-8"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
cj=http.cookiejar.CookieJar()
for k,v in ck.items():
    cj.set_cookie(http.cookiejar.Cookie(0,k,v,None,False,".bilibili.com",False,False,"/",True,False,None,False,None,None,{}))
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders=[("User-Agent",UA),("Referer","https://member.bilibili.com/platform/upload-manager/article")]
# 先确认登录态
d=json.loads(op.open("https://api.bilibili.com/x/web-interface/nav",timeout=20).read().decode())
print("nav:", d.get("code"), (d.get("data") or {}).get("uname"))
aid=117561643505239
body={"aid":aid,"csrf":ck["bili_jct"],"title":"test"}
for ep in ["https://member.bilibili.com/x/vu/web/edit","https://member.bilibili.com/x/vu/client/edit","https://member.bilibili.com/x/web/archives/edit"]:
    u=f"{ep}?csrf={ck['bili_jct']}"
    try:
        req=urllib.request.Request(u,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
        r=op.open(req,timeout=30).read().decode()
        print(ep.split('/x/')[1], "->", r[:150])
    except Exception as e:
        print(ep.split('/x/')[1], "ERR", str(e)[:60])
