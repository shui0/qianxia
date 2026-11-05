# 舞萌 DX 模块（apps/maimai）

给群友用的曲库与评分查询。纯标准库，不依赖第三方包，不联网（除了刷新数据）。

```
apps/maimai/
├─ maimai.py        核心：加载 / 搜索 / 谱面解析 / rating 计算
├─ cli.py           命令行入口
├─ update_data.py   从查分器公开接口刷新曲库
├─ tests.py         自测（22 条，python tests.py）
└─ data/music_data.json   1405 首曲目（SD 543 / DX 862）
```

## 用法

```powershell
$py = "D:\cosmos\miniconda3\envs\gptsovits\python.exe"
cd apps\maimai

& $py cli.py count                      # 曲库规模
& $py cli.py search Grievous            # 搜曲
& $py cli.py song ヒバナ --notes         # 看某首的全部谱面（含物量、谱师）
& $py cli.py rating --ds 13.8 --ach 100.5   # 算单谱面 rating
& $py update_data.py                    # 新曲上线后刷新
```

作为库调用：

```python
import maimai
songs = maimai.load()
hit = maimai.search(songs, "Grievous")[0]
print(maimai.format_song(hit))          # 适合直接发群里的文本
print(maimai.chart_rating(13.8, 100.5)) # 309
```

## 谱面类型：ST / DX / 宴

同一首歌在游戏里可能有两张完全不同的谱面，定数也不同，输出里用标签区分：

| 标签 | 数据里的 type | 说明 |
|---|---|---|
| 【ST】 | SD | 标准谱面 |
| 【DX】 | DX | DX 谱面（多数新曲只有这个） |
| 【宴】 | utage | 宴会场谱面（**公开数据源目前不含，见下**） |

同名曲会**一起显示**（先 ST 后 DX），`--style st|dx` 可以只看其中一种。

> 宴会场：查分器公开接口只给 ST/DX，宴谱没有开放数据。真要支持得另找来源
> （社区整理的 utage 表），落成 `data/utage.json` 后按同样结构并进来即可。

## 数据

来源：<https://www.diving-fish.com/api/maimaidxprober/music_data>（查分器的公开接口，只读、免登录）。
每首歌带 `title / type / ds[] / level[] / charts[] / basic_info{artist,bpm,genre,from}`。

另有两条同样来自查分器的接口：

| 接口 | 用途 | 是否要 token |
|---|---|---|
| `music_data` | 全量曲目、定数、谱面物量 | 否 |
| `chart_stats` | 每张谱面的**拟合定数**、平均达成率、游玩次数 | 否 |
| `query/player` | 按查分器用户名查 b50（对方需注册并公开） | 否 |

拟合定数是社区用真实成绩拟出来的实际难度，比官方定数更能说明问题（例：ヒバナ MASTER 官方 12.0，拟合 12.22）。

刷新后曲库会覆盖 `data/music_data.json`，旧文件不保留备份（数据是公开的，随时可重拉）。

## 别名表

中文俗称、罗马字、B 站喊法大多对不上数据里的正式曲名，所以在 `data/aliases.json` 里维护了一张映射：

```json
{ "命嫌": "命に嫌われている", "六兆年": "六兆年と一夜物語", "砂星": "砂の惑星 feat. HATSUNE MIKU" }
```

搜索时先过别名表，命中会提示「别名『命嫌』→ 命に嫌われている」。管理命令：

```powershell
& $py cli.py alias list
& $py cli.py alias add 命嫌 "命に嫌われている"   # 会先校验曲库里有没有这首
& $py cli.py alias remove 命嫌
```

## rating 公式

单谱面 rating = `floor(定数 × 系数 × 100)`，系数按达成率取档：

| 达成率 | 系数 | | 达成率 | 系数 |
|---|---|---|---|---|
| ≥100.5% | 0.224 | | ≥94% | 0.168 |
| ≥100% | 0.216 | | ≥90% | 0.152 |
| ≥99.5% | 0.211 | | ≥80% | 0.136 |
| ≥99% | 0.208 | | ≥75% | 0.120 |
| ≥98% | 0.203 | | ≥70% | 0.104 |
| ≥97% | 0.200 | | ≥60% | 0.096 |
| | | | ≥50% | 0.088 |

例：`13.8 × 100.5%` → `13.8 × 0.224 = 3.0912` → **309 分**。

总 rating 取 best 35 旧谱 + best 15 新谱之和（本模块只算单谱面）。

## 已知限制

- **只认原题**：数据里是日文/英文原名，中文俗称、B 站梗名（如「舞萌」指游戏本身）搜不到；
  需要的话可以加一张别名表。
- 曲库是社区维护的，新曲可能滞后几天，跑一次 `update_data.py` 即可。
- 谱面物量来自 `charts[].notes`（Tap/Hold/Slide/Touch 四项之和），部分老谱为空。

## 后续接入机器人

计划作为一个插件工具暴露，形状大概：

```
qqbot_maimai(action="search", query="Grievous")
qqbot_maimai(action="song",   query="ヒバナ")
qqbot_maimai(action="rating", ds=13.8, ach=100.5)
```

群里说「千夏 XXX 多少级」「这首多少分」就能直接答。
