# -*- coding: utf-8 -*-
"""生成 16:9 封面：同款蓝底 + 千夏 + 大字标题"""
import sys

sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\apps\video")
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BG = r"C:\Users\baizh\.dsh\bot\workspace\assets\bg_ref.png"
ART = r"C:\Users\baizh\.dsh\bot\workspace\assets\chinatsu_raw.webp"
OUT = r"C:\Users\baizh\.dsh\bot\workspace\apps\video\out\cover_01.jpg"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"

W, H = 1920, 1080
bg = Image.open(BG).convert("RGB").resize((W, H), Image.LANCZOS)

art = Image.open(ART).convert("RGBA")
HAT_TOP, CHIN, FACE_X = 40, 470, 400
scale = (H * 0.95) / (CHIN - HAT_TOP)
big = art.resize((int(art.width * scale), int(art.height * scale)), Image.LANCZOS)
x = int(W * 0.30 - FACE_X * scale)
y = int(-40)
bg.paste(big, (x, y), big)

d = ImageDraw.Draw(bg)
# 右侧标题
lines = ["你是哪种", "音游佬？"]
f = ImageFont.truetype(FONT, 150)
yy = H * 0.30
mask = Image.new("L", (W, H), 0)
md = ImageDraw.Draw(mask)
for ln in lines:
    md.text((W * 0.60, yy), ln, font=f, fill=255)
    yy += 175
mask = mask.filter(ImageFilter.GaussianBlur(10))
bg = Image.composite(Image.new("RGB", (W, H), (10, 26, 52)), bg, mask.point(lambda v: min(255, int(v * 1.2))))
d = ImageDraw.Draw(bg)
yy = H * 0.30
for ln in lines:
    d.text((W * 0.60, yy), ln, font=f, fill=(255, 255, 255), stroke_width=6, stroke_fill=(20, 40, 70))
    yy += 175

f2 = ImageFont.truetype(FONT, 62)
d.text((W * 0.60, H * 0.72), "千夏配音 · 神人鉴定", font=f2, fill=(255, 255, 255))

bg.save(OUT, quality=95)
print("saved", OUT, bg.size)
