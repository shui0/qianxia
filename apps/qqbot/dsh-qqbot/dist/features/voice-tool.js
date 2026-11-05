/**
 * 语音条（二次加工新增）—— 自建云端推理版
 *
 * 链路：文本 → 你自己的推理服务（HTTP）→ 音频文件 → QQ 语音
 *
 * 设计成"只认接口、不认模型"：
 *   插件这边不关心你后端跑的是 GPT-SoVITS、CosyVoice 还是别的，
 *   只要满足下面的契约，就能直接发声。
 *
 * 接口契约（POST 到 config.voice.endpoint）：
 *   请求体 JSON: { text: string, speaker?: string, format?: 'wav'|'mp3' }
 *   响应二选一：
 *     ① 直接返回音频字节，Content-Type: audio/wav 或 audio/mpeg
 *     ② 返回 JSON: { url: "https://..../x.wav" } 或 { audio: "<base64>" }
 *
 * 为什么要三种：自建服务有时直接流式吐音频，有时先写到对象存储返回链接，
 * 有时干脆塞 base64。三种都认，你后端怎么写都行。
 */
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { sendMediaFile } from '../media/send-media.js';
import { getMemoryStore } from '../features/memory-store.js';

export const SAY_TOOL_NAME = 'qqbot_say';

function voiceDir() {
    const mem = getMemoryStore();
    const root = mem?.root ?? resolve(process.cwd(), 'qq-memory');
    const dir = join(root, 'voice');
    try { mkdirSync(dir, { recursive: true }); } catch { /* ignore */ }
    return dir;
}

/** 把服务端的响应变成落盘的音频文件，返回 { path, ext } */
export function materializeAudio(res, { dir = voiceDir(), stub = Math.random().toString(36).slice(2) } = {}) {
    const ct = String(res.contentType ?? '').toLowerCase();
    const base = join(dir, `say-${Date.now()}-${stub}`);
    const save = (buf, ext) => {
        const p = `${base}.${ext}`;
        writeFileSync(p, buf);
        return { path: p, ext };
    };
    // ① 二进制音频
    if (ct.startsWith('audio/')) {
        const ext = ct.includes('mpeg') || ct.includes('mp3') ? 'mp3' : ct.includes('ogg') ? 'ogg' : 'wav';
        return Promise.resolve(save(res.buffer, ext));
    }
    // ② JSON 形态
    return (async () => {
        let j;
        try { j = JSON.parse(res.buffer.toString('utf8')); } catch { throw new Error('语音服务返回了看不懂的内容'); }
        if (typeof j.audio === 'string' && j.audio.length > 0) {
            return save(Buffer.from(j.audio, 'base64'), j.format === 'mp3' ? 'mp3' : 'wav');
        }
        if (typeof j.url === 'string' && /^https?:\/\//.test(j.url)) {
            const r = await fetch(j.url);
            if (!r.ok) throw new Error(`下载音频失败 ${r.status}`);
            const buf = Buffer.from(await r.arrayBuffer());
            const ext = j.url.toLowerCase().endsWith('.mp3') ? 'mp3' : 'wav';
            return save(buf, ext);
        }
        throw new Error('语音服务返回的 JSON 里既没有 audio 也没有 url');
    })();
}

export function registerSayTool(ctx, mediaSender, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_say 工具未注册');
        return;
    }
    const definition = {
        name: SAY_TOOL_NAME,
        description: 'Speak a line out loud: turn text into a voice message and send it to the current QQ conversation. '
            + 'Use only when the user asks for voice (说句话 / 语音回我 / 用声音说). '
            + 'Keep the text short (under 60 Chinese characters) — it is a chat voice note, not a podcast.',
        parameters: {
            type: 'object',
            properties: {
                text: { type: 'string', description: 'What to say. Keep it short and in the character voice.' },
                speaker: { type: 'string', description: 'Optional speaker/model id understood by your inference server.' },
            },
            required: ['text'],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: {
                    ok: { type: 'boolean' },
                    chars: { type: 'integer' },
                    ext: { type: 'string' },
                },
                required: ['ok'],
                additionalProperties: false,
            },
            render: (_a, v) => [{ type: 'text', text: v.ok ? `已发送语音（${v.chars} 字）` : '语音没发出去' }],
        },
        async execute(args, exec) {
            const cfg = config.voice ?? {};
            if (cfg.enabled !== true) throw new Error('qqbot_say: 语音功能未启用（config.voice.enabled）');
            if (!cfg.endpoint) throw new Error('qqbot_say: 没有配置推理服务地址（config.voice.endpoint）');
            const text = String(args.text ?? '').trim();
            if (!text) throw new Error('qqbot_say: 没有内容要念');
            if (text.length > 200) throw new Error('qqbot_say: 太长了，语音说不完（上限 200 字）');

            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), Math.max(3000, Number(cfg.timeoutMs) || 30000));
            let res;
            try {
                const r = await fetch(cfg.endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(cfg.token ? { Authorization: `Bearer ${cfg.token}` } : {}),
                    },
                    body: JSON.stringify({ text, speaker: args.speaker ?? cfg.speaker ?? undefined, format: cfg.format ?? 'wav' }),
                    signal: controller.signal,
                });
                if (!r.ok) throw new Error(`推理服务返回 ${r.status}`);
                res = { contentType: r.headers.get('content-type'), buffer: Buffer.from(await r.arrayBuffer()) };
            }
            finally {
                clearTimeout(timer);
            }

            const audio = await materializeAudio(res, { dir: voiceDir() });
            const replyTarget = exec.agent !== undefined
                ? manager.findByAgent(exec.agent)?.replyTarget
                : undefined;
            if (!replyTarget) throw new Error('qqbot_say: 找不到当前会话，发不出去');

            const sent = await sendMediaFile(mediaSender, replyTarget, audio.path);
            if (sent.outcome !== 'sent') throw new Error(`qqbot_say: 语音发送失败 ${sent.error ?? sent.outcome}`);
            logger.info(`im-qqbot: 语音已发送 ${text.length} 字 → ${replyTarget.scope}:${replyTarget.targetId}`);
            return { ok: true, chars: text.length, ext: audio.ext };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_say 工具已注册');
}
