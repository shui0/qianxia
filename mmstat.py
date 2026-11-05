import json, collections
p=r"C:\Users\baizh\.dsh\bot\workspace\apps\maimai\data\music_data.json"
songs=json.load(open(p,encoding="utf-8"))
print("type 分布:", collections.Counter(s["type"] for s in songs))
utage=[s for s in songs if s["type"] not in ("SD","DX")]
print("非 SD/DX 条目:", len(utage))
for s in utage[:5]: print("  ", s["type"], s["title"], s["ds"])
# 同名 ST+DX 的情况
from collections import defaultdict
by=defaultdict(list)
for s in songs: by[s["title"]].append(s["type"])
both=[t for t,v in by.items() if "SD" in v and "DX" in v]
print("同时有 ST/DX 的歌:", len(both), "例:", both[:3])
