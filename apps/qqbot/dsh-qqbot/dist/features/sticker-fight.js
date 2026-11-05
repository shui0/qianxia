/**
 * 斗图模式（二次加工新增）
 *
 * 有人在群里喊"斗图/来图/再来一张"，或者连发表情包时，她不是回一句话，
 * 而是**连发几张**，中间插一句短的。
 *
 * 为什么做成"一次性爆发"而不是"进入状态持续监听"：
 *   持续监听意味着每来一张图她都要被唤醒一次，既费 token 又容易失控
 *   （一群人斗图能把她刷成刷屏机器人）。一次调用发 N 张，N 有硬上限，
 *   发完就结束，最可控。
 */
import { scanLibrary, search } from '../media/sticker-tool.js';
import { sendMediaFile } from '../media/send-media.js';

const MAX_BURST = 5;

/**
 * 从库里挑 n 张**不重复**的。
 * 优先满足 query；query 命中不了就走"优先目录随机"。
 */
export function pickBurst(library, count, query, prefer = [], rng = Math.random) {
    const n = Math.max(1, Math.min(MAX_BURST, Number(count) || 3));
    const picked = [];
    const used = new Set();
    let guard = 0;
    while (picked.length < n && guard < n * 12) {
        guard += 1;
        const { pick } = search(library, query, { prefer });
        if (!pick) break;
        if (used.has(pick.path)) continue;
        used.add(pick.path);
        picked.push(pick);
    }
    // 命中数不够就随机补（从优先目录里补，补不齐再用全库）
    if (picked.length < n) {
        const preferSet = new Set(prefer);
        let pool = library.filter((s) => preferSet.size === 0 || preferSet.has(s.top));
        if (pool.length === 0) pool = library;
        const rest = pool.filter((s) => !used.has(s.path));
        for (let i = rest.length - 1; i > 0; i -= 1) {
            const j = Math.floor(rng() * (i + 1));
            [rest[i], rest[j]] = [rest[j], rest[i]];
        }
        for (const s of rest) {
            if (picked.length >= n) break;
            used.add(s.path);
            picked.push(s);
        }
    }
    return picked;
}

/** 连发：每张之间隔 gapMs，最后返回发出去几张 */
export async function sendBurst({ mediaSender, target, library, count, query, prefer = [], gapMs = 2500, logger }) {
    const picks = pickBurst(library, count, query, prefer);
    let sent = 0;
    for (const s of picks) {
        try {
            const r = await sendMediaFile(mediaSender, target, s.path);
            if (r.outcome === 'sent') sent += 1;
        }
        catch (err) {
            logger?.warn?.(`im-qqbot[fight]: 发送失败 ${s.name}: ${err instanceof Error ? err.message : String(err)}`);
        }
        if (sent < picks.length) await new Promise((res) => setTimeout(res, Math.max(0, gapMs)));
    }
    return sent;
}

/** 库和配置都从 config 里取，供工具调用 */
export async function runFight({ mediaSender, target, config, count, query, logger }) {
    const dir = config?.sticker?.dir || '';
    const library = dir ? scanLibrary(dir) : [];
    if (library.length === 0) return { ok: false, reason: 'empty-library' };
    const n = Math.max(1, Math.min(MAX_BURST, Number(count) || Number(config?.stickerFight?.count) || 3));
    const gap = Math.max(0, Number(config?.stickerFight?.gapMs) || 2500);
    const sent = await sendBurst({
        mediaSender, target, library, count: n, query,
        prefer: config?.sticker?.prefer ?? [], gapMs: gap, logger,
    });
    return { ok: sent > 0, sent, total: library.length };
}
