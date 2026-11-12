"""命令行入口：查曲、算分。

    python cli.py search Grievous
    python cli.py song  "Grievous Lady"
    python cli.py rating --ds 13.8 --ach 100.5
    python cli.py count
"""
from __future__ import annotations

import argparse
import json
import sys

import bindings
import records
import maimai


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="舞萌 DX 曲库 / 评分查询")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="按标题搜索")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)

    d = sub.add_parser("song", help="看一首歌的全部谱面")
    d.add_argument("query")
    d.add_argument("--notes", action="store_true", help="显示物量与谱师")
    d.add_argument("--limit", type=int, default=5)
    d.add_argument("--style", choices=["st","dx","all"], default="all", help="只看标准谱/只看DX谱")

    r = sub.add_parser("rating", help="按定数与达成率算单谱面 rating")
    r.add_argument("--ds", type=float, required=True)
    r.add_argument("--ach", type=float, required=True)

    sub.add_parser("count", help="曲库规模")

    p = sub.add_parser("player", help="按查分器用户名 / QQ号 / 绑定查成绩")
    p.add_argument("username", nargs="?", default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--qq", help="按绑定的 QQ 号查")
    p.add_argument("--openid", help="按群成员 openid 查（需先 bind）")
    p.add_argument("--fallback-qq", help="没有绑定时按此 QQ 号查 B50")
    p.add_argument("--json", action="store_true", help="输出完整 B50 JSON")
    p.add_argument("--refresh", action="store_true", help="忽略缓存，强制重拉")
    p.add_argument("--all", action="store_true", help="查全部成绩（需要导入令牌），并给出推分建议")

    b = sub.add_parser("bind", help="绑定 QQ 身份 ↔ 查分器账号")
    b.add_argument("--openid", required=True)
    b.add_argument("--qq", help="QQ 号")
    b.add_argument("--username", help="查分器用户名")
    b.add_argument("--token", help="导入令牌（查全部成绩用，存在本地）")

    a = sub.add_parser("alias", help="管理别名表")
    a.add_argument("op", choices=["list", "add", "remove"])
    a.add_argument("alias", nargs="?")
    a.add_argument("title", nargs="?")

    args = ap.parse_args(argv)

    if args.cmd == "alias":
        aliases = maimai.load_aliases()
        if args.op == "list":
            if not aliases:
                print("（空）")
            for k, v in aliases.items():
                print(f"{k}  →  {v}")
            return 0
        if args.op == "add" and (not args.alias or not args.title):
            print("用法：alias add <别名> <正式曲名>")
            return 2
        if args.op == "remove" and not args.alias:
            print("用法：alias remove <别名>")
            return 2
        if args.op == "add":
            songs_all = maimai.load()
            if not maimai.search(songs_all, args.title, limit=1, aliases={}):
                print(f"曲库里没有「{args.title}」，先确认正式曲名")
                return 1
            maimai.save_alias(args.alias, args.title)
            print(f"已添加：{args.alias} → {args.title}")
            return 0
        ok = maimai.delete_alias(args.alias)
        print("已删除" if ok else "没这个别名")
        return 0 if ok else 1

    if args.cmd == "bind":
        try:
            if not args.qq and not args.username and args.token:
                records.set_token(args.openid, args.token)
                print("已保存导入令牌。")
                return 0
            rec = bindings.bind(args.openid, qq=args.qq, username=args.username)
            if args.token:
                records.set_token(args.openid, args.token)
        except ValueError as e:
            print(f"绑定失败：{e}")
            return 2
        print(f"已绑定：{args.openid} → {rec.get('qq') or rec.get('username')}")
        return 0

    if args.cmd == "player" and getattr(args, "all", False):
        analysis, source = records.analyze(args.openid, top=args.top, refresh=args.refresh)
        if analysis.get("ok") is False or "total" not in analysis:
            print(f"拿不到全成绩：{analysis.get('error')}")
            print("（需要在查分器「设置 → 导入令牌」复制令牌，然后说「我的令牌是 xxx」）")
            return 1
        print(maimai.format_push(analysis))
        return 0

    if args.cmd == "player":
        data, source = bindings.fetch(
            openid=args.openid, qq=args.qq, username=args.username, refresh=args.refresh,
            fallback_qq=args.fallback_qq,
        )
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
            return int(data.get("ok") is False)
        if data.get("ok") is False:
            print(f"查不到：{data.get('error')}")
            print("（对方需要先在查分器注册、绑定 QQ 并公开成绩）")
            return 1
        tag = "（缓存）" if source == "cache" else ""
        print(maimai.format_player(data, top=args.top) + (f"\n{tag}" if tag else ""))
        return 0

    songs = maimai.load()

    if args.cmd == "count":
        dx = sum(1 for x in songs if x.get("type") == "DX")
        print(f"共 {len(songs)} 首（SD {len(songs) - dx} / DX {dx}）")
        return 0

    if args.cmd == "rating":
        print(maimai.format_rating(args.ds, args.ach))
        return 0

    aliases = maimai.load_aliases()
    resolved, hit = maimai.resolve_alias(args.query, aliases)
    if hit:
        print(f"（别名「{hit}」→ {resolved}）\n")

    hits = maimai.search(songs, args.query, limit=args.limit, aliases=aliases)
    if not hits:
        print(f"没找到「{args.query}」")
        return 1

    if args.cmd == "search":
        for song in hits:
            info = song.get("basic_info") or {}
            tops = [c for c in maimai.charts(song) if c.name in ("MASTER", "Re:MASTER")]
            top = tops[-1] if tops else None
            extra = f"  {top.level}({top.ds:g})" if top else ""
            print(f"【{maimai.type_label(song.get('type', ''))}】{song.get('title')}  {info.get('artist', '')}{extra}")
        return 0

    title = hits[0].get("title", "")
    entries = maimai.same_title(songs, title)
    if getattr(args, "style", "all") != "all":
        want = "ST" if args.style == "st" else "DX"
        entries = [e for e in entries if maimai.type_label(e.get("type", "")) == want] or entries
    print(maimai.format_entries(entries, with_notes=args.notes))
    if len(hits) > 1:
        others = "、".join(h.get("title", "") for h in hits[1:] if h.get("title") != title)
        if others:
            print(f"\n（还有相近的：{others}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
