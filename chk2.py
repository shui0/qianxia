import sys
sys.path.insert(0, r"C:\Users\baizh\.dsh\bot\workspace\apps\maimai")
import maimai
songs = maimai.load()
e = maimai.same_title(songs, "六兆年と一夜物語")
t = maimai.format_entries(e)
print("同名条目:", len(e), "| ST:", "【ST】" in t, "| DX:", "【DX】" in t, "| 拟合:", "拟合" in t)
r = maimai.query_player("一定不存在的用户名xyz")
print("玩家接口:", r.get("ok"), r.get("error"))
