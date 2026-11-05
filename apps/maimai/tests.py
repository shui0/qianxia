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

# ── 别名 ──
import os
import tempfile

aliases = maimai.load_aliases()
check("别名表非空", len(aliases) >= 10, f"实际 {len(aliases)}")

bad = [k for k, v in aliases.items() if not maimai.search(songs, v, limit=1, aliases={})]
check("每个别名都指向真实曲目", bad == [], f"坏的: {bad}")

resolved, hit = maimai.resolve_alias("命嫌", aliases)
check("别名能解析", resolved == "命に嫌われている" and hit == "命嫌", f"{resolved} / {hit}")

resolved, hit = maimai.resolve_alias("不存在的别名", aliases)
check("未知别名原样返回", resolved == "不存在的别名" and hit is None)

hits = maimai.search(songs, "命嫌")
check("用别名能搜到曲", hits and hits[0]["title"] == "命に嫌われている", str(hits[:1]))

hits = maimai.search(songs, "六兆年")
check("别名搜到带后缀的歌", hits and hits[0]["title"] == "六兆年と一夜物語")

hits = maimai.search(songs, "KING", aliases={})
check("关闭别名时按原名搜", hits and hits[0]["title"] == "KING")

with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "aliases.json")
    maimai.save_alias("测试别名", "ヒバナ", path=p)
    got = maimai.load_aliases(path=p)
    check("别名能写入并读回", got.get("测试别名") == "ヒバナ", str(got))
    check("别名能删除", maimai.delete_alias("测试别名", path=p) is True)
    check("删不存在的别名返回 False", maimai.delete_alias("没有这个", path=p) is False)

print(f"\n通过 {passed} / 失败 {failed}")
raise SystemExit(1 if failed else 0)
