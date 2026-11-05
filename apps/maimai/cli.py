"""命令行入口：查曲、算分。

    python cli.py search Grievous
    python cli.py song  "Grievous Lady"
    python cli.py rating --ds 13.8 --ach 100.5
    python cli.py count
"""
from __future__ import annotations

import argparse
import sys

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

    r = sub.add_parser("rating", help="按定数与达成率算单谱面 rating")
    r.add_argument("--ds", type=float, required=True)
    r.add_argument("--ach", type=float, required=True)

    sub.add_parser("count", help="曲库规模")

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
            print(f"{song.get('title')}  [{song.get('type')}]  {info.get('artist', '')}{extra}")
        return 0

    song = hits[0]
    print(maimai.format_song(song, with_notes=args.notes))
    if len(hits) > 1:
        others = "、".join(h.get("title", "") for h in hits[1:])
        print(f"\n（还有相近的：{others}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
