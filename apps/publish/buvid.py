import json, urllib.request, http.cookiejar
ck=json.load(open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json",encoding="utf-8"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"
spi=json.load(urllib.request.urlopen(urllib.request.Request("https://api.bilibili.com/x/frontend/finger/spi",headers={"User-Agent":UA}),timeout=20))
b3=spi["data"]["b_3"]; b4=spi["data"].get("b_4","")
ck["buvid3"]=b3; ck["buvid4"]=b4
json.dump(ck, open(r"C:\Users\baizh\.dsh\bot\workspace\apps\publish\cookies.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("buvid3", b3[:20], "keys", list(ck))
