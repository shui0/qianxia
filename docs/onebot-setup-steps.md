# OneBot 接入步骤（dsh-qq-onebot + NapCat）

> 目标：用一个 QQ 小号当机器人，群里不 @ 也能接话，人格是日向千夏。
> 已准备好的东西：`C:\Users\baizh\.dsh\bot\workspace\napcat\OneKey\NapCatInstaller.exe`（已下载解压）

---

## 第 0 步：先想清楚

- NapCat 是「QQ 协议端」，**违反腾讯用户协议**，账号有被风控/封禁风险。
- **必须用小号**，别用主号；最好别和主号同一台设备频繁切换。
- 已经装好的官方机器人（`@tencent-connect/dsh-qqbot`）可以留着，两者不冲突，但同一个群里两个 bot 都在会抢话，建议只留一个。

---

## 第 1 步：装 NapCat，登录小号

1. 双击 `C:\Users\baizh\.dsh\bot\workspace\napcat\OneKey\NapCatInstaller.exe`
2. 它会**单独装一份 QQ**（不碰你现在用的 QQ），装到它自己指定的目录。
3. 装完启动，用**小号**扫码登录。
4. 打开 WebUI：`http://127.0.0.1:6099`（首次可能要扫码/输 token）。
5. 「网络配置」→ 新建 **WebSocket 服务器**：

| 项 | 填 |
|---|---|
| 地址 | `127.0.0.1` |
| 端口 | `3001` |
| Token | 自己编，比如 `qianxia-2026` |
| 消息格式 | `array` ← 选错这个一定收不到消息 |

> 杀进程别用 `Get-Process -Name QQ | Stop-Process`，会把你自己在用的 QQ 一起杀掉。

---

## 第 2 步：装插件（必须完全退出 DSH）

`dsh-qq-onebot` 要写进 profile 的 node_modules，DSH 开着装会文件占用失败。

1. **完全退出 DSH**：托盘图标右键 → 退出（不是关窗口）。
2. 打开 PowerShell，执行：

```powershell
& "D:\dsh\resources\runtime\cli\bin\dsh.cmd" plugin --profile desktop add dsh-qq-onebot
```

3. 重新打开 DSH。
4. 确认装上了：**设置 → 插件** 里能看到 `dsh-qq-onebot`；或执行
   `& "D:\dsh\resources\runtime\cli\bin\dsh.cmd" plugin --profile desktop why dsh-qq-onebot`

---

## 第 3 步：填连接信息

**设置 → QQ** 面板里填 `wsUrl` 和 `accessToken`，点「重连」。

面板没出现的话，直接建文件（约 800ms 自动生效）：

`C:\Users\baizh\.dsh\dsh-qq\settings.json`

```json
{
  "wsUrl": "ws://127.0.0.1:3001",
  "accessToken": "qianxia-2026",
  "requireMention": false,
  "groupMode": "allowlist",
  "groupAllow": ["你的测试群号"],
  "groupReplyGapMs": 20000,
  "rateLimitPerMin": 8,
  "privateMode": "allowlist",
  "privateAllow": ["你的QQ号"]
}
```

日志里出现「已连接 ws://127.0.0.1:3001」就通了。日志在
`C:\Users\baizh\.dsh\profiles\desktop\logs\dsh-qq-<日期>.log`。

---

## 第 4 步：人设

「设置 → QQ」→ 它人设 → `persona` 里贴日向千夏那段（见 `hinata-chinatsu-qq-prompt.md`）。

也可以直接改 `settings.json` 加一个 `persona` 字段，但 JSON 里长文本要转义，用面板更省事。

---

## 排障速查

| 现象 | 原因 |
|---|---|
| 一直重连 | `wsUrl` 没填 / NapCat 的 WS 没启用 / token 两边不一致 |
| 收到的消息是空的 | NapCat 消息格式选了 `string`，要 `array` |
| 私聊不理人 | `privateMode` 默认 `allowlist` 且白名单是空的 |
| 群里不 @ 就不理 | `requireMention` 还是 `true` |
| 每条消息回两遍 | 两个宿主同时连着 NapCat（同一台只能一个） |
| 发不出去但不报错 | WS 和 HTTP 是两个不同的 token，填串了 |

---

## 提醒

- 每句话都是一次模型调用，**会烧 token**。先用 `groupAllow` 限定测试群，`rateLimitPerMin` 压到 8 左右。
- `workspaceRoot` 指到哪，它就能在哪读写文件，别指到你的代码仓库根目录。
- 走到这一步如果觉得「为了不 @ 也回话，付出封号风险 + 长期维护」不划算，官方机器人那条路其实是更稳的选择——只是群里必须由群主开「获取群内全部消息」。
