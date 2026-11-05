"""舞萌模块的自测（不依赖 pytest，直接 python tests.py）。

覆盖：评分公式边界、搜索命中顺序、Re:MASTER 解析、名人名言式的异常输入。
"""
from __future__ import annotations

import maimai

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"PASS  {name}")
        passed += 1
    else:
        print(f"FAIL  {name}  {detail}")
        failed += 1


songs = maimai.load()

# ── 评分公式 ──
check("100.5% 用最高系数", maimai.coefficient(100.5) == 0.224)
check("99.3% 落 99 档", maimai.coefficient(99.3) == 0.208)
check("97.5% 落 97 档", maimai.coefficient(97.5) == 0.200)
check("75% 边界", maimai.coefficient(75.0) == 0.120)
check("74.9% 掉到 70 档", maimai.coefficient(74.9) == 0.104)
check("0% 最低档", maimai.coefficient(0) == 0.080)

check("13.8 @100.5% = 309", maimai.chart_rating(13.8, 100.5) == 309)
check("14.2 @99.3% = 295", maimai.chart_rating(14.2, 99.3) == 295)
check("14.0 @100% = 302", maimai.chart_rating(14.0, 100.0) == 302)
check("rating 是向下取整", maimai.chart_rating(13.0, 100.0) == 280)

# ── 曲库 ──
check("曲库规模合理", len(songs) > 1000, f"实际 {len(songs)}")

hits = maimai.search(songs, "Grievous Lady")
check("英文精确命中", hits and hits[0]["title"] == "Grievous Lady", str(hits[:1]))

hits = maimai.search(songs, "ヒバナ")
check("日文命中", hits and hits[0]["title"] == "ヒバナ")

hits = maimai.search(songs, "grievous lady")   # 大小写不敏感
check("大小写不敏感", hits and hits[0]["title"] == "Grievous Lady")

hits = maimai.search(songs, "GrievousLady")    # 空格不敏感
check("空格不敏感", hits and hits[0]["title"] == "Grievous Lady")

hits = maimai.search(songs, "zzzzzzzzzzzzzzz")
check("查不到返回空", hits == [])

# ── 谱面解析 ──
song = maimai.search(songs, "ヒバナ")[0]
cs = maimai.charts(song)
check("谱面数量与 ds 对齐", len(cs) == len(song["ds"]))
check("难度名正确", cs[0].name == "BASIC")
check("Re:MASTER 能解析", any(c.name == "Re:MASTER" for c in cs))
check("物量能求和", all(c.notes is None or c.notes > 0 for c in cs))

text = maimai.format_song(song, with_notes=True)
check("格式化包含标题", "ヒバナ" in text)
check("格式化包含定数", "13.2" in text)

print(f"\n通过 {passed} / 失败 {failed}")
raise SystemExit(1 if failed else 0)
