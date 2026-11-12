# 千夏独立 QQ 机器人

千夏通过 NoneBot2 的 OneBot v11 适配器接收 QQ 消息。NapCatQQ 负责小号登录。支持私聊、群聊 @ 对话，或在群消息句首用“千夏”稳定唤醒，例如“千夏，在吗”“千夏帮我看看”。唤醒后直接处理，不经过随机接话的概率、延迟和冷却；聊天、看图、帮助和搜图都支持，群白名单仍然生效。仅在句中提到名字不算直接唤醒。最近六轮成功对话、好感度和情绪保存在本地 SQLite 数据库中。

## Windows 本地运行

在 PowerShell 进入仓库下的 `apps/qqbot/standalone`，执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

编辑 `.env`，用随机值替换 `ONEBOT_V11_ACCESS_TOKEN`，填写模型服务的 OpenAI 兼容基础地址、模型名和密钥。建议先把 `QIANXIA_GROUPS` 填成测试群 ID 列表，如 `[123456789]`。空列表允许所有群。默认使用仓库的 `docs/prompt19-direct.txt` 与 `docs/prompt19-group.txt`。

```powershell
.\.venv\Scripts\python.exe bot.py
```

在 NapCat 端扫码登录小号。在网络配置中新增 **WebSocket 客户端**，填写 `ws://127.0.0.1:8080/onebot/v11/ws`，设置与 `ONEBOT_V11_ACCESS_TOKEN` 一致的 Token，并启用该配置。先私聊小号发一条文本，再到测试群 @ 小号发一条文本。

[NoneBot OneBot v11 连接文档](https://onebot.adapters.nonebot.dev/docs/guide/setup/) · [NapCatQQ 项目](https://github.com/NapNeko/NapCatQQ)

## 本机守护

本机已切换 NapCat Framework 有头接入。QQ 使用独立副本 `napcat/headful-qq-official-49738/QQ.exe`，通过官方 Framework 包内的 `napimain.exe`、`napiloader.dll` 和 `nativeLoader.cjs` 加载；不依赖 LiteLoader，也不修改日常系统 QQ。完整 QQ 窗口可以最小化到托盘。OneBot、后台 Token、千夏插件及数据沿用原配置。

`napcat/active-mode.json` 的 `mode=framework` 指定当前入口，`Start-NapCatFramework.ps1` 检查同路径 QQ 已运行时不会重复启动。原 Node 接入目录保留作回退，守护每次只选择一种方式。切换前的配置和守护脚本备份在 `napcat/backups/framework-20261111-201613`。有头模式是否长期改善掉线仍需观察；QQ 强制安全验证时仍需本人操作。

Windows 任务计划程序中的 `Qianxia Standalone Watchdog` 在当前 Windows 用户登录时检查一次，平时每 2 小时在后台静默检查千夏、NapCat、本地 Qwen、GPT-SoVITS（9880）和语音适配层（8000）进程。进程退出时会重新启动，运行中的进程会保留。语音服务复用本机 `D:\gptsovits\repo`、Conda 的 `gptsovits` 环境和 `apps/voice/.env` 配置。NapCat 启动时可以尝试复用已登录过的小号会话，QQ 要求扫码或验证时在 NapCat WebUI 完成。

守护日志在 `logs/watchdog.log`。需要暂停自动拉起时，在任务计划程序禁用该任务。

## 添加插件

自己的 Python 插件放进 `plugins/`，重启即按项目配置加载。安装社区插件时，在本目录用虚拟环境中的 NB-CLI：

```powershell
.\.venv\Scripts\python.exe -m pip install nb-cli
.\.venv\Scripts\nb.exe plugin install <插件包名>
```

挑选兼容 OneBot v11 的插件。命令类插件可用 NoneBot 默认的匹配优先级，匹配后阻止传播，优先于千夏的对话处理器。

## 已迁移指令

| 功能 | QQ 指令及配置 |
| --- | --- |
| 舞萌 | `/舞萌 搜曲 曲名`、`/舞萌 谱面 曲名`、`/舞萌 评分 13.8 100.5`、`/舞萌 曲库`、`/舞萌 B50 [用户名]`、`/舞萌 绑定 用户名`、`/舞萌 推分`。导入令牌仅通过私聊 `/舞萌 令牌 令牌值` 接收。 |
| 语音 | `/语音 要念的文字`。默认请求本机 `8000/tts`，本机守护会自动启动现有 FastAPI 与 GPT-SoVITS。 |
| 看图 | 群里 @千夏并附上图片，或引用图片后 @千夏提问；私聊直接发图。图片和文字一起交给当前视觉模型，沿用千夏人设。每次最多3张，动图只看第一帧；同一用户在同一会话10分钟内可继续问“刚才那张图”。图片最多短暂缓存在32个会话内，不保存到数据库或磁盘；重启后失效。超大、损坏或下载失败会直接提示，不拿旧图回答。图片最长边缩至768，细小文字可单独裁剪后再发。模型服务需支持 OpenAI image_url 输入，并加载视觉组件；本机 Qwen 已加载。`QIANXIA_VISION_ENABLED=false` 可关闭。 |
| 联网 | `/搜索 关键词`、`/联网 关键词`；也可以直接聊天。默认使用 Exa 高级检索，同时取得每页至多 2 万字正文与 3000 字相关段落；匿名模式有限流，可在本机用 `QIANXIA_EXA_API_KEY` 配置自己的 Key。故障时回退 DDGS 的 Bing/Yahoo。公开名单类问题和近期事实先检索，其他公开知识出现不确定草稿时先查证。最多选 3 个来源，只有摘要的来源再通过 Exa 批量补抓至多 6 万字正文；按问题保留相关段落及表头，证据总预算约 1800 字符。参考资料问题不混入未请求的排行榜字段。阅读模型拒答时最多补做一次原文摘录，程序验证来源编号及原文连续匹配后才接受，然后继续使用千夏语气回复。正文失败保留摘要并明确标记，不能保证动态页面数据或网页完整性；`QIANXIA_SEARCH_READ_ENABLED=false` 关闭正文读取。资料不足明确未知，成功回答附来源。阶段诊断在 `logs/search-stages.jsonl`，不保存问题明文或网页全文。个人感受和主动随机接话不强制搜索。 |
| 日服新曲 | 日服官方目录独立缓存在 `data/maimai-jp.json`；每天 08:00（UTC+8）后台刷新，启动时补齐过期数据，失败保留旧数据。直接问 `aegisfortia` 等目录曲名会先查证。国服查分数据不受影响。刷新进程和下一次执行时间在 `data/maimai-jp.schedule.json`。 |
| B 站 | `/B站 搜索 关键词`、`/B站 详情 BV号`、`/B站 评论 BV号`。如需启用发评，配置 `apps/publish/cookies.json` 和 `QIANXIA_BILI_POST_USERS`，再在私聊用 `/B站 发评论 BV号 内容` 预演，按回复指示确认。 |
| Pixiv 找图 | `/搜图 日向千夏 5`，别名 `/找图`、`/pixiv`；默认1张，每轮最多5张。指令和“找张星空的图”等明确句式优先直接执行，其余自然说法由 AI 调用 `search_images` 工具，例如“来5张日向千夏”。规则与 AI 共用对话上下文，记下真实成功图片数，支持继续说“再来两张”；不清楚角色时由 AI 澄清。纯功能询问、内部分类和主动随机接话不触发发图。`QIANXIA_PIXIV_AI_ENABLED=false` 可关闭 AI 工具入口并保留指令。每次真实请求 Pixiv 检索，检查全年龄、单页和精确标签；跳过多页合集，优先标题匹配，在同等相关候选中随机选。每会话跳过最近成功发出的20张作品及相同文件，群内共用、私聊独立，跨关键词生效，记录在记忆数据库 `pixiv_recent` 表，重启保留。最多查3页，候选不足不重复凑数；20张窗口外的旧图可再次出现。发送预览、作者及原作链接，链接回退/失败不记已发图片。默认系统代理或 `QIANXIA_PIXIV_PROXY`；`QIANXIA_PIXIV_ENABLED=false` 可关闭全部搜图。公开接口变化或站点限制会明确提示失败。 |
| 记忆与群报 | `/好感度`、`/心情`、`/日记`、`/日记 写`、`/周报`。普通群消息仅在 `QIANXIA_MEMORY_GROUPS` 指定群记录，周报最多统计最近 800 条，群日记使用本群当天的记录。 |
| 表情与游戏 | `/表情包 [关键词]`、`/斗图 [关键词]`、`/骰子 2d6`、`/猜数字`、`/抽一个`。表情包目录默认使用仓库外置的 `stickers`，可通过 `QIANXIA_STICKER_DIR` 改路径。 |
| 菜单 | `/菜单` 或只 @ 小号，返回文本指令列表。 |
| 主动接话 | 默认在可回复的群启用。用 `QIANXIA_PROACTIVE_ENABLED=false` 关闭，或用 `QIANXIA_PROACTIVE_GROUPS` 限定启用群。聊到舞萌、音击、时代剧、爬树或野外探险等兴趣点会触发，其他消息默认有 5% 概率触发。两种方式共用 25 秒延迟和 180 秒群冷却。可通过 `QIANXIA_PROACTIVE_KEYWORDS`、`QIANXIA_PROACTIVE_PROBABILITY`、`QIANXIA_PROACTIVE_DELAY` 和 `QIANXIA_PROACTIVE_COOLDOWN` 调整。 |

`/舞萌 B50` 输出一张包含 B35 和 B15 的成绩图。不带参数时优先使用已有的查分器绑定。没有绑定时直接查询当前发送者的 QQ 号。查全量成绩需要本人的水鱼导入令牌，推分仅限私聊。

设置 `QIANXIA_DEFENSE_OWNER_QQ` 可开启群聊护主。千夏根据原始 @ 或引用回复识别对象。对优先保护账号的明确异议、质疑或攻击会逐条判断并反驳，同一消息只处理一次。对其他成员仍只介入明显人身攻击，每群默认冷却 120 秒，可通过 `QIANXIA_DEFENSE_COOLDOWN` 调整。千夏会引用原消息并 @ 发言者。

未 @ 或引用时，千夏会参考同群最近 90 秒的短时上下文。只有能确认对方在反驳优先保护账号时才介入。护主使用的这份短时上下文保存在内存里。

独立版状态默认放在仓库根目录的 `qq-memory/standalone.sqlite3`。原 DSH 的历史记录和账号映射保留在原目录。新插件通过 QQ 指令直接触发，B 站发评默认关闭。

## 自测

默认的私聊和群聊人设保留 19 岁同人背景。语感参考 [SEGA 日向千夏角色页](https://ongeki.sega.jp/character/1140/)及[《千夏の潜入大作戦》章节公告](https://ongeki.sega.jp/news/20200115/)，提示词里的中文聊天示例为原创。

联网回答、日记和反驳共用 `qianxia_persona.py` 中的简短千夏语气规则，功能结果和失败提示也采用口语。联网先独立核对正文，再把答案改成千夏的说法，并检查所列名称和数值是否保留；改写失败时直接用自然引导语列出原条目。回复不展开资料完整性、排除项等内部说明，末尾仅保留实际使用的来源及原编号。命令结果的数值、命令、确认码、图片和语音不经过模型改写。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
