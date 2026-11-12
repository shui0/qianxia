import asyncio
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT_PATHS = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
)
DIFFICULTIES = ("BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER")
WIDTH, MARGIN, GAP, COLUMNS, CARD_HEIGHT = 1520, 32, 12, 5, 96
CARD_WIDTH = (WIDTH - 2 * MARGIN - (COLUMNS - 1) * GAP) // COLUMNS
COVER_SIZE = 76
MAX_COVER_BYTES = 1024 * 1024
cover_cache: OrderedDict[int, Image.Image] = OrderedDict()


def fit(text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    text = " ".join(text.split())
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + "…") > width:
        text = text[:-1]
    return text + "…"


def b50_sections(data: dict):
    charts = data.get("charts") or {}
    return [
        ("B35 · 旧版本", "#4769c9", sorted(charts.get("sd") or [], key=lambda row: -int(row.get("ra") or 0))[:35]),
        ("B15 · 新版本", "#087f76", sorted(charts.get("dx") or [], key=lambda row: -int(row.get("ra") or 0))[:15]),
    ]


def cover_id(row: dict) -> int | None:
    value = row.get("song_id")
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        return None
    digits = str(value)
    if not digits.isascii() or not digits.isdecimal() or len(digits) > 7:
        return None
    number = int(digits)
    return number - 10000 if 10000 < number <= 11000 else number or None


async def fetch_cover(client: httpx.AsyncClient, song_id: int) -> Image.Image | None:
    try:
        async with client.stream("GET", f"/covers/{song_id:05d}.png") as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_COVER_BYTES:
                    return None
        with Image.open(BytesIO(data), formats=["PNG"]) as source:
            if max(source.size) > 2048:
                return None
            return ImageOps.fit(source.convert("RGB"), (128, 128), Image.Resampling.LANCZOS)
    except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def load_b50_covers(data: dict) -> dict[int, Image.Image]:
    song_ids = dict.fromkeys(song for _, _, rows in b50_sections(data)
                             for row in rows if (song := cover_id(row)) is not None)
    covers = {}
    for song in song_ids:
        if song in cover_cache:
            cover_cache.move_to_end(song)
            covers[song] = cover_cache[song]
    missing = [song for song in song_ids if song not in covers]
    if not missing:
        return covers

    async with httpx.AsyncClient(
        base_url="https://www.diving-fish.com", timeout=6,
        limits=httpx.Limits(max_connections=12),
    ) as client:
        async def load(song: int):
            cover = await fetch_cover(client, song)
            if cover is not None:
                covers[song] = cover
                cover_cache[song] = cover
                cover_cache.move_to_end(song)
                if len(cover_cache) > 256:
                    cover_cache.popitem(last=False)

        try:
            async with asyncio.timeout(14):
                await asyncio.gather(*(load(song) for song in missing))
        except TimeoutError:
            pass
    return covers


def make_background(height: int, art: list[Image.Image]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, height), "#101b34")
    if art:
        collage = Image.new("RGB", (256, 256))
        for index in range(4):
            collage.paste(art[index % len(art)], (128 * (index % 2), 128 * (index // 2)))
        backdrop = ImageOps.fit(collage, image.size, Image.Resampling.BICUBIC)
        image = Image.blend(image, backdrop.filter(ImageFilter.GaussianBlur(54)), .38)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((MARGIN, 18, WIDTH - MARGIN, 119), radius=20, fill=(9, 19, 40, 184))
    draw.line((MARGIN + 20, 119, WIDTH - MARGIN - 20, 119), fill=(119, 220, 255, 110), width=2)
    return image


def render_b50(data: dict, covers: dict[int, Image.Image] | None = None) -> bytes:
    sections = b50_sections(data)
    if not any(rows for _, _, rows in sections):
        raise ValueError("查分器没有返回可显示的 B50 成绩。")
    font_path = next((path for path in FONT_PATHS if path.is_file()), None)
    if font_path is None:
        raise RuntimeError("未找到中文字体")
    title_font, name_font, small_font, score_font = (
        ImageFont.truetype(str(font_path), size) for size in (40, 19, 15, 23)
    )
    section_heights = [48 + max(1, (len(rows) + COLUMNS - 1) // COLUMNS) * (CARD_HEIGHT + GAP)
                       for _, _, rows in sections]
    covers = covers or {}
    featured_ids = dict.fromkeys(song for _, _, rows in sections
                                 for row in rows if (song := cover_id(row)) in covers)
    featured = [covers[song] for song in list(featured_ids)[:4]]
    image = make_background(140 + sum(section_heights) + MARGIN, featured)
    draw = ImageDraw.Draw(image)
    name = str(data.get("nickname") or data.get("username") or "玩家")
    draw.text((MARGIN + 20, 30), "舞萌 DX · BEST 50", font=title_font, fill="#ffffff")
    draw.text((MARGIN + 22, 84), fit(name, name_font, 950), font=name_font, fill="#c9dcff")
    draw.text((WIDTH - MARGIN - 22, 45), f"Rating  {data.get('rating') or 0}", anchor="ra",
              font=title_font, fill="#ffffff")

    top = 140
    for (label, color, rows), height in zip(sections, section_heights):
        section_rating = sum(int(row.get("ra") or 0) for row in rows)
        draw.text((MARGIN, top), f"{label}   {len(rows)} 条   ·   {section_rating} 分",
                  font=score_font, fill="#ffffff")
        if not rows:
            draw.text((MARGIN, top + 50), "暂无成绩", font=name_font, fill="#c9dcff")
        for index, row in enumerate(rows):
            column, line = index % COLUMNS, index // COLUMNS
            x = MARGIN + column * (CARD_WIDTH + GAP)
            y = top + 43 + line * (CARD_HEIGHT + GAP)
            draw.rounded_rectangle((x, y, x + CARD_WIDTH, y + CARD_HEIGHT), radius=10, fill="white")
            artwork = covers.get(cover_id(row))
            if artwork is None:
                draw.rounded_rectangle((x + 9, y + 10, x + 9 + COVER_SIZE, y + 10 + COVER_SIZE),
                                       radius=5, fill="#e5edf8")
                draw.text((x + 47, y + 49), "无曲绘", anchor="mm", font=small_font, fill=color)
            else:
                thumb = artwork.resize((COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS)
                image.paste(thumb, (x + 9, y + 10))
            text_x = x + COVER_SIZE + 19
            draw.text((text_x, y + 8), fit(str(row.get("title") or "未知曲目"), name_font, CARD_WIDTH - COVER_SIZE - 30),
                      font=name_font, fill="#17213b")
            level = row.get("level_index")
            difficulty = DIFFICULTIES[level] if isinstance(level, int) and 0 <= level < len(DIFFICULTIES) else "谱面"
            chart_type = "ST" if row.get("type") == "SD" else "DX"
            draw.text((text_x, y + 38), f"{index + 1:02d}  {chart_type} · {difficulty} · {row.get('ds') or '—'}",
                      font=small_font, fill="#53627c")
            draw.text((text_x, y + 64), f"{float(row.get('achievements') or 0):.4f}%",
                      font=small_font, fill="#394764")
            draw.text((x + CARD_WIDTH - 11, y + 56), str(row.get("ra") or 0), anchor="ra",
                      font=score_font, fill=color)
        top += height

    result = BytesIO()
    image.save(result, "PNG")
    return result.getvalue()
