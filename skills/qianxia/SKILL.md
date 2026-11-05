---
name: qianxia
description: 操作「千夏」项目：DSH 的 QQ 机器人插件、GPT-SoVITS 语音适配层、蓝底视频流水线、B 站投稿。当需要起语音服务、合成一句话、出一支视频、投稿，或改动机器人能力（记忆/好感/日记/周报/斗图/小游戏/情绪）时使用。
---

# 千夏项目（qianxia）

四个子应用共用一个 Python 环境和一套素材，各自独立运行：

| 子应用 | 位置 | 职责 |
|---|---|---|
| QQ 机器人 | `apps/qqbot/dsh-qqbot/` | DSH 插件源码；实际生效的是 profile 下 `node_modules/@tencent-connect/dsh-qqbot/dist` |
| 语音 | `apps/voice/` | FastAPI 适配层，`POST /tts {text,speaker}` → 音频字节 |
| 蓝底视频 | `apps/video/` | 文案 → 配音 → 卡片动画 → MP4 |
| B 站投稿 | `apps/publish/` | 扫码登录、投稿、查状态 |

## 先决条件（缺一个就跑不通）

- Python：`D:\cosmos\miniconda3\envs\gptsovits\python.exe`（torch 2.7.0+cu128，50 系显卡必须用 cu128 构建）
- ffmpeg：`D:\cosmos\miniconda3\envs\gptsovits\Scripts\ffmpeg.exe`
- GPT-SoVITS 本体：`D:\gptsovits\repo`，权重在其 `GPT_SoVITS/pretrained_models/`（约 3.9 GB）
- 第三方库：调用前挂 `PYTHONPATH`，否则 `import bilibili_api` 会失败
  ```powershell
  $env:PYTHONPATH="$PWD\tools\ytdlp;$PWD\tools\biliapi;$PWD\tools\qrimg"
  ```

## 任务 1：起语音服务

```powershell
copy start-voice.example.bat start-voice.bat   # 首次：填自己的 python / GPT-SoVITS / 参考音频路径
.\start-voice.bat                              # 起 9880 推理 + 8000 适配层，约 20 秒就绪
curl http://127.0.0.1:8000/healthz             # {"ok":true,"speakers":[...]}
```

合成一句：

```powershell
curl -X POST http://127.0.0.1:8000/tts -H "Content-Type: application/json" `
     -d '{"text":"诶嘿，千夏在这里哦","speaker":"qingxia","format":"wav"}' -o out.wav
```

接口约定：`POST /tts` 返回三种形态都接受——`audio/wav` 字节、`{"audio":"<base64>"}`、`{"url":"https://..."}`。
参考音频（3~10 秒干声）+ 对应文字决定音色；换音色只改 `start-voice.bat` 里的 `REF_AUDIO_*` / `REF_TEXT_*`。

## 任务 2：出一支蓝底视频

```powershell
cd apps\video
& "D:\cosmos\miniconda3\envs\gptsovits\python.exe" make_video.py --script script_02.txt --out out\new.mp4
& "D:\cosmos\miniconda3\envs\gptsovits\python.exe" make_cover.py
```

关键参数：`--size 1080x1350`（9:16 写 `1080x1920`）、`--style cert|bust`、`--no-typing`、`--gap 0.32`。
脚本会调 8000 端口的语音服务，**语音服务没起会直接失败**。

## 任务 4：查舞萌曲目 / 算分

```powershell
cd apps\maimai
$py = "D:\cosmos\miniconda3\envs\gptsovits\python.exe"
& $py cli.py search Grievous                     # 搜曲，输出「曲名 [SD/DX] 谱师 最高难度(定数)」
& $py cli.py song ヒバナ --notes                  # 全部谱面：等级(定数) 物量 谱师
& $py cli.py rating --ds 13.8 --ach 100.5        # 单谱面 rating → 309
& $py cli.py alias list                          # 俗称表；add/remove 可维护
& $py tests.py                                   # 22 条自测
& $py update_data.py                             # 新曲上线后刷新曲库
```

作为库用：`import maimai; songs = maimai.load(); maimai.search(songs, "Grievous")`。

**坑**：只认原题（日文/英文），中文俗称和梗名搜不到；rating = `floor(定数 × 系数 × 100)`，
系数按达成率取档（≥100.5% → 0.224，≥97% → 0.200，≥80% → 0.136 …），总 rating 是 best35 旧谱 + best15 新谱。

## 任务 3：用机器人已有能力

机器人在 DSH 里以插件运行，工具名固定，直接调用即可：

| 工具 | 用途 |
|---|---|
| `qqbot_say` | 文本 → 语音条（需要语音服务在跑） |
| `qqbot_group_report` | 群周报（话痨榜/热词/名场面），数据来自 `qq-memory/` |
| `qqbot_diary` | 写/读日记，`action: write/read/draft` |
| `qqbot_affinity` | 查好感度，`name` 省略则看排行 |
| `qqbot_send_sticker` | 从 `stickers/` 发一张表情包 |
| `qqbot_sticker_fight` | 斗图，连发 1~5 张 |
| `qqbot_minigame` | 骰子 / 抽人 / 猜数字 |
| `qqbot_send_file` | 发本地文件到当前会话 |

改插件代码：改 `apps/qqbot/dsh-qqbot/dist/`，覆盖到 profile 的 `node_modules/.../dist/`，再 touch
`cordis.patch.yml` 触发热重载（**已加载的模块不会热更，改已有文件需重启 DSH**）。

## 排错表（都踩过）

| 现象 | 原因 / 解法 |
|---|---|
| `pip` 装 torch 卡在 0 MB/s | Windows 下 pip 会读系统代理；`$env:NO_PROXY="*"` 或关代理 |
| 阿里云 pytorch 镜像只有 0.2 MB/s | 单连接限速；用分块并行下载（`archive/` 里有脚本） |
| HF 下模型 0 速度 | 换 ModelScope；`AI-ModelScope/GPT-SoVITS` 实测 11 MB/s |
| `No module named 'jieba_fast'` | 需 MSVC 编译；改用纯 Python `jieba`，把 `jieba_fast` 全部替换为 `jieba` |
| `No module named 'pkg_resources'` | setuptools ≥81 移除了它；`pip install "setuptools<81"` |
| `fast-langdetect: Cache directory not found` | 首次调用会自动下 `lid.176.bin`(125 MB) 到 `pretrained_models/fast_langdetect/` |
| `sm_120 / no kernel image` | torch 不是 cu128 构建；装 `torch==2.7.0+cu128` |
| 本地请求 502 | 适配层需 `trust_env=False`，否则被系统代理劫持 |
| 投稿替换报 `21001` / `-101` | 接口受限，改就重投一条，旧的手动删 |

## 不要做

- 不要把 `apps/publish/cookies.json`、`start-voice.bat`、`qq-memory/`、`assets/`、`stickers/` 提交进仓库（`.gitignore` 已拦）
- 不要用未经许可的真人/声优音频当参考音源
- 不要在 DSH 运行中手改 profile 的 `package.json` / lockfile，装插件用 `dsh plugin add`
