# 千夏语音服务（自建云端推理）

把插件发来的文本变成语音，返回给 QQ。推理本身交给 GPT-SoVITS（或任何能吐音频的服务）。

```
QQ 插件 (qqbot_say)
   │  POST {text, speaker}
   ▼
app.py（本目录，协议适配层）
   │  POST /tts {text, ref_audio_path, ...}
   ▼
GPT-SoVITS api_v2.py  ← 真正跑模型的地方（GPU）
   │  audio/wav
   ▼
插件 → SDK 转 silk → 群里一条语音
```

## 接口契约

插件只认这个形状，你后端换成 CosyVoice / Bert-VITS2 也一样：

```
POST /tts
{"text": "诶嘿，千夏在这儿！", "speaker": "qingxia", "format": "wav"}

200 → audio/wav 字节
```

也支持返回 JSON（插件端已兼容）：

- `{"audio": "<base64>", "format": "wav"}`
- `{"url": "https://.../x.wav"}`

## 部署（以 RunPod / AutoDL 为例）

1. **起 GPT-SoVITS 的 API**
   ```bash
   python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
   ```

2. **把模型和参考音频放上去**
   ```
   /models/ref/qingxia.wav     # 参考音频（3~10 秒，干净无 BGM）
   ```

3. **起本服务**
   ```bash
   pip install -r requirements.txt
   GPT_SOVITS_URL=http://127.0.0.1:9880/tts \
   REF_AUDIO_QINGXIA=/models/ref/qingxia.wav \
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

4. **对外开放**（RunPod 给的是 8000 端口映射；自建机记得开防火墙 / 加 token）

5. **回到 DSH 配插件**
   ```yaml
   voice:
     enabled: true
     endpoint: https://你的地址/tts
     token: 一串自己编的密钥
     speaker: qingxia
     format: wav
     timeoutMs: 30000
   ```

## 关于参考音频（重要）

`/models/ref/*.wav` 决定了"听起来像谁"。**请用你有权使用的音源**：自己录的、明确授权的、或原创虚拟歌手的。放未经许可的真人/声优音频，等于克隆真人的声音，出了事是实打实的法律问题——这也是我不提供、也不会帮你找模型的原因。

## 开销参考

| 项 | 量级 |
|---|---|
| GPU | 单卡 8G 显存够跑 GPT-SoVITS 推理 |
| 延迟 | 一句话 1~3 秒（含网络） |
| 成本 | RunPod 按小时计费，闲时关掉 |

## 本地测试

```bash
curl -X POST http://127.0.0.1:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"诶嘿，千夏在这儿！","speaker":"qingxia"}' \
  -o test.wav
```
