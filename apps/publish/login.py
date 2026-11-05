# -*- coding: utf-8 -*-
"""B站扫码登录：生成二维码 + 轮询状态，成功后把 cookie 存到 cookies.json"""
import json
import os
import sys
import time
import urllib.request
import http.cookiejar

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\tools\qrimg")
import qrcode

WS = r"C:\Users\baizh\.dsh\bot\workspace\apps\publish"
os.makedirs(WS, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
     "Referer": "https://www.bilibili.com/"}

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = list(H.items())

gen = json.loads(op.open("https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                         timeout=20).read().decode("utf-8"))
if gen.get("code") != 0:
    raise SystemExit(f"生成二维码失败: {gen}")
data = gen["data"]
url, key = data["url"], data["qrcode_key"]
print("URL:", url)
print("KEY:", key)

img = qrcode.make(url, box_size=9, border=2)
png = os.path.join(WS, "login_qr.png")
img.save(png)
print("QR:", png)

deadline = time.time() + 170
last = None
while time.time() < deadline:
    time.sleep(2.5)
    try:
        r = json.loads(op.open(
            f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={key}",
            timeout=15).read().decode("utf-8"))
    except Exception as e:
        print("poll err", str(e)[:60], flush=True)
        continue
    code = (r.get("data") or {}).get("code")
    if code != last:
        print("status", code, (r.get("data") or {}).get("message"), flush=True)
        last = code
    if code == 0:
        cookies = {c.name: c.value for c in cj}
        with open(os.path.join(WS, "cookies.json"), "w", encoding="utf-8") as fh:
            json.dump(cookies, fh, ensure_ascii=False, indent=1)
        print("LOGIN OK, cookies:", list(cookies), flush=True)
        break
else:
    print("TIMEOUT")
