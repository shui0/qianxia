"""命令行入口：逛 B 站 / 发评论。

    python cli.py search 桥姬
    python cli.py info BV1xx411c7mD
    python cli.py comments BV1xx411c7mD
    python cli.py post BV1xx411c7mD "说一句" --yes   # 不加 --yes 只预演
    python cli.py whoami
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import bili


def _print_search(items):
    if not items:
        print("没搜到")
        return
    for it in items:
        print(f"{it['title']}")
        print(f"  UP: {it['author']} · {bili._fmt_num(it['play'])} 播放 · {it['duration']} · {it['bvid']}")


def _print_info(info):
    print(f"{info['title']}")
    print(f"  UP: {info['owner']} · {info['bvid']}")
    print(f"  {bili._fmt_num(info['view'])} 播放 · {bili._fmt_num(info['like'])} 赞 · "
          f"{bili._fmt_num(info['reply'])} 评论 · 时长 {bili._fmt_time(info['duration'])}")
    if info.get("desc"):
        desc = info["desc"].replace("\n", " ")
        print(f"  简介: {desc[:160]}{'…' if len(desc) > 160 else ''}")


def _print_comments(items):
    if not items:
        print("没有评论")
        return
    for it in items:
        text = it["text"].replace("\n", " ")
        print(f"[{it['like']} 赞] {it['user']}: {text[:110]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="逛 B 站")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("keyword")
    s.add_argument("--limit", type=int, default=5)

    i = sub.add_parser("info")
    i.add_argument("bvid")

    c = sub.add_parser("comments")
    c.add_argument("bvid")
    c.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("post")
    p.add_argument("bvid")
    p.add_argument("text")
    p.add_argument("--yes", action="store_true", help="真的发出去（不加只预演）")

    sub.add_parser("whoami")

    args = ap.parse_args(argv)

    if args.cmd == "search":
        _print_search(asyncio.run(bili.search_videos(args.keyword, limit=args.limit)))
        return 0
    if args.cmd == "info":
        _print_info(asyncio.run(bili.video_info(args.bvid)))
        return 0
    if args.cmd == "comments":
        _print_comments(asyncio.run(bili.top_comments(args.bvid, limit=args.limit)))
        return 0
    if args.cmd == "whoami":
        r = asyncio.run(bili.whoami())
        print(r)
        return 0 if r.get("ok") else 1
    if args.cmd == "post":
        if not args.yes:
            print(f"[预演] 会在 {args.bvid} 下评论：{args.text}")
            print("确认发送请加 --yes")
            return 0
        r = asyncio.run(bili.send_comment(args.bvid, args.text))
        print(r)
        return 0 if r.get("ok") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
