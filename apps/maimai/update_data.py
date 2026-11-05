"""刷新曲库数据（从查分器公开接口拉全量曲目）。

    python update_data.py

数据源：https://www.diving-fish.com/api/maimaidxprober/music_data
只读公开接口，不需要登录、不需要 token。新曲上线后跑一次即可。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "music_data.json")
URL = "https://www.diving-fish.com/api/maimaidxprober/music_data"


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": "qianxia-maimai/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    songs = json.loads(raw.decode("utf-8"))
    if not isinstance(songs, list) or len(songs) < 100:
        print("返回内容不像曲库，放弃写入", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(songs, fh, ensure_ascii=False)
    dx = sum(1 for s in songs if s.get("type") == "DX")
    print(f"已更新 {len(songs)} 首（SD {len(songs) - dx} / DX {dx}）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
