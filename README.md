# 千夏项目（qianxia）

使用 QQ 小号独立运行千夏，请见 [NoneBot2 + NapCat 启动说明](apps/qqbot/standalone/README.md)。

一个仓库，四个子应用：**QQ 机器人**、**语音合成**、**蓝底视频**、**B 站投稿**。
它们共用同一套 Python 环境与同一份素材，但独立运行、互不阻塞。

```
workspace/
├─ README.md                  ← 你在这里（项目总入口）
├─ start-voice.bat            ← 一键起语音服务（9880 推理 + 8000 适配层）
│
├─ apps/                      ← 所有可运行的应用
│   ├─ qqbot/dsh-qqbot/       QQ 机器人插件源码（dsh-qqbot 改造版）
│   ├─ voice/                 语音合成适配层（FastAPI，:8000）
│   ├─ video/                 蓝底视频流水线（文案 → 配音 → 成片）
│   ├─ publish/               B 站投稿（登录 / 投稿 / 查状态）
│   ├─ maimai/                舞萌 DX 曲库与评分查询（1405 首，纯标准库）
│   └─ bili/                  逛 B 站：搜索 / 视频信息 / 评论 / 发评论
│
├─ assets/                    素材：立绘 chinatsu_raw.webp、蓝底底图 bg_ref.png
├─ stickers/                  QQ 表情包库（152 张，音击/舞萌/中二）
├─ qq-memory/                 机器人记忆：消息、档案、日记、情绪、指令面板
│
├─ tools/                     第三方 Python 库（yt-dlp / bilibili-api / qrcode），用 PYTHONPATH 挂载
├─ docs/                      人设 prompt、调研笔记
├─ logs/  literature/         运行日志 / 零散资料
├─ napcat/                    NapCat 安装包（备用协议端，未启用）
└─ archive/                   归档：patches、tests、scratch、legacy
```

## 给 Agent 的操作手册（skill）

`skills/qianxia/SKILL.md` 是一份可被 Agent 直接加载的技能：触发条件、前置路径、可直接粘贴的命令、还有一张踩坑排错表。
人类看 README 知道"有什么"，Agent 读 skill 才知道"怎么跑"——两者互补，别只留一个。

## 环境

| 项 | 路径 |
|---|---|
| Python | `D:\cosmos\miniconda3\envs\gptsovits\python.exe`（torch 2.7.0+cu128 / funasr / Pillow） |
| ffmpeg | `D:\cosmos\miniconda3\envs\gptsovits\Scripts\ffmpeg.exe` |
| GPT-SoVITS | `D:\gptsovits\repo`（推理服务 `api_v2.py`，:9880） |
| 第三方库 | 调用前加 `$env:PYTHONPATH="$PWD\tools\ytdlp;$PWD\tools\biliapi;$PWD\tools\qrimg"` |

## 1. QQ 机器人（apps/qqbot）

机器人在 DSH 里以插件形式运行，**生效的代码在 profile 下**：

```
C:\Users\baizh\.dsh\profiles\desktop\node_modules\@tencent-connect\dsh-qqbot\dist\
```

`apps/qqbot/dsh-qqbot/` 是源码副本，两边应逐字节一致（改完要覆盖过去并触发热重载）。

已实现能力：长期记忆 / 好感度 / 日记 / 群周报 / 斗图 / 小游戏 / 情绪状态机 / 指令面板 / 语音条。
配置全部在：

```
C:\Users\baizh\.dsh\profiles\desktop\cordis.patch.yml   →  im-qqbot 段
```

合并进来的模块（原插件没有的）在 `dist/features/`：`memory-store` `mood` `diary` `group-report`
`reply-policy` `proactive-talk` `sticker-fight` `minigame` `affinity-tool` `menu` `panel` `voice-tool`。

## 2. 语音合成（apps/voice）

```powershell
.\start-voice.bat              # 起 9880 推理 + 8000 适配层
curl http://127.0.0.1:8000/healthz
curl -X POST http://127.0.0.1:8000/tts -H "Content-Type: application/json" `
     -d '{"text":"诶嘿，千夏在这里哦","speaker":"qingxia","format":"wav"}' -o test.wav
```

- 接口契约：`POST /tts {text, speaker, format}` → 返回音频字节（也支持 `{audio:base64}` / `{url}`）
- 参考音频与语种在 `start-voice.bat` 的环境变量里（`REF_AUDIO_*` / `REF_LANG_*`），换音色只改这里
- 适配层用 `trust_env=False`，**不会被系统代理劫持**（踩过的坑：开梯子后本地请求 502）
- 实测：单句 1.1 秒，显存 1.5 GB

> 注：`voice-server/` 是整理前的旧路径，当前运行中的进程 cwd 还锁在那儿；
> 服务下次重启后可以删掉，之后只保留 `apps/voice/`。

## 3. 蓝底视频（apps/video）

```powershell
cd apps\video
$py = "D:\cosmos\miniconda3\envs\gptsovits\python.exe"

& $py make_video.py --script script_02.txt --out out\new.mp4   # 出片
& $py make_cover.py                                            # 16:9 封面
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--size` | `1080x1350` | 想要 9:16 写 `1080x1920` |
| `--style` | `cert` | `cert`=证件照构图，`bust`=半身 |
| `--typing` / `--no-typing` | 开 | 字幕逐字出现 |
| `--title` / `--index` | 关 | 角标 / 序号 |
| `--gap` | 0.32 | 句尾留白秒数 |

产物在 `apps/video/out/`，参考素材在 `apps/video/refs/`，一次性采集脚本在 `apps/video/tools/`（平时不用跑）。

## 4. B 站投稿（apps/publish）

```powershell
cd apps\publish
& $py login.py      # 扫码，写 cookies.json
& $py publish.py    # 投稿（改脚本里的 VIDEO/TITLE/DESC/TAGS/TID）
& $py list.py       # 查状态
```

已知限制：替换已发布稿件（`web/edit` 报 21001、`client/edit` 报 -101）与删除稿件（需极验验证码）
走不通，要改就重投一条、旧的去创作中心手动删。

## 5. 舞萌曲库（apps/maimai）

群友问「这首多少级」「打这个能加多少分」时用。纯标准库，不联网。

```powershell
cd apps\maimai
$py = "D:\cosmos\miniconda3\envs\gptsovits\python.exe"

& $py cli.py search Grievous          # 搜曲
& $py cli.py song ヒバナ --notes       # 全部谱面（物量、谱师）
& $py cli.py rating --ds 13.8 --ach 100.5   # → 309
& $py cli.py alias list                 # 俗称表（命嫌/六兆年/砂星…）
& $py tests.py                        # 22 条自测
& $py update_data.py                  # 新曲上线后刷新曲库
```

数据来自查分器公开接口（只读免登录），rating 公式与限制见 `apps/maimai/README.md`。

## 6. 逛 B 站（apps/bili）

读：搜索、看视频信息、读热门评论（匿名即可）。
写：发评论需要登录态（`apps/publish/cookies.json`）。

```powershell
cd apps\bili
$env:PYTHONPATH = "C:\Users\baizh\.dsh\bot\workspace\tools\biliapi"
& $py cli.py search 桥姬
& $py cli.py info BV1xx411c7mD
& $py cli.py comments BV1xx411c7mD
& $py cli.py post BV1xx411c7mD "内容"        # 预演
& $py cli.py post BV1xx411c7mD "内容" --yes  # 真发
& $py cli.py whoami
```

机器人侧对应 `qqbot_bili`：发评论必须带 `confirm=true`，且先复述内容让用户确认。

## 注意

- `apps/publish/cookies.json` 是登录态，别外传、别提交
- 成片与素材体积大，不建议进 git
- 立绘与声音涉及第三方素材，公开发布有被限流/下架的风险，自己评估

## 本次整理（2026-11-05）

- `voice-server/ video/ bili/` → `apps/voice/`、`apps/video/`、`apps/publish/`
- `fork/dsh-qqbot/` → `apps/qqbot/dsh-qqbot/`，`fork/` 空目录已删
- 脚本内的绝对路径同步改写（`workspace\video` → `workspace\apps\video` 等），共 23 个文件
- `start-voice.bat` 指向 `apps\voice`
- `archive/tests/` 里 18 个测试的相对 import 已同步
- 校验：全部 Python 文件 `py_compile` 通过（0 错误），无残留旧路径引用
