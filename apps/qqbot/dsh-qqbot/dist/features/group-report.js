/**
 * 群周报（二次加工新增）
 *
 * 数据全部来自本地长期记忆（qq-memory/messages/*.jsonl），不碰任何平台接口。
 * 输出一段纯文本，适合直接发群里。
 *
 * 统计口径：
 *   - 消息数 / 发言人数
 *   - 话痨榜：按消息条数取前 3
 *   - 热词：复用 memory-store 的朴素 n-gram 提取
 *   - 名场面：长度 12~60 字的句子随机挑 3 条（太短没信息量，太长刷屏）
 *   - 活跃时段：按小时分桶取峰值
 */
import { getMemoryStore } from "./memory-store.js";

/** 从消息数组算出报告所需的全部统计 */
export function computeStats(entries) {
    const byUser = new Map();
    const hourBuckets = new Array(24).fill(0);
    const texts = [];
    for (const e of entries) {
        const name = e.n || (e.s ? String(e.s).slice(0, 8) : '某人');
        byUser.set(name, (byUser.get(name) ?? 0) + 1);
        const h = new Date(e.t).getHours();
        if (Number.isFinite(h)) hourBuckets[h] += 1;
        if (typeof e.c === 'string' && e.c.trim()) texts.push(e.c.trim());
    }
    const talkers = [...byUser.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
    const peakHour = hourBuckets.indexOf(Math.max(...hourBuckets));
    return {
        total: entries.length,
        people: byUser.size,
        talkers,
        peakHour: hourBuckets[peakHour] > 0 ? peakHour : -1,
        texts,
    };
}

/** 挑"名场面"：长度适中、不是纯表情、去重 */
export function pickQuotes(entries, limit = 3, rng = Math.random) {
    const pool = [];
    const seen = new Set();
    for (const e of entries) {
        const c = typeof e.c === 'string' ? e.c.trim() : '';
        if (c.length < 12 || c.length > 60) continue;
        if (/^\[[^\]]*\]$/.test(c)) continue; // 纯附件标签
        if (/^\[表情\]$/.test(c)) continue; // 纯表情
        if (/<face|faceType|<@|\[CQ:|https?:\/\//i.test(c)) continue; // 残留标记/链接
        if (seen.has(c)) continue;
        seen.add(c);
        pool.push({ text: c, name: e.n || (e.s ? String(e.s).slice(0, 8) : '某人') });
    }
    // 洗牌后取前 N，避免每次都挑同样几条
    for (let i = pool.length - 1; i > 0; i -= 1) {
        const j = Math.floor(rng() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, limit);
}

function fmtDate(ts) {
    const d = new Date(ts);
    return `${d.getMonth() + 1}/${d.getDate()}`;
}

/** 组装成可以直接发群里的文本 */
export function formatReport({ entries, days = 7, topicsOf, rng = Math.random }) {
    if (!entries || entries.length === 0) {
        return `📊 这${days}天群里还没什么动静，千夏攒不出周报诶……`;
    }
    const s = computeStats(entries);
    const topics = typeof topicsOf === 'function' ? topicsOf(s.texts).slice(0, 5) : [];
    const quotes = pickQuotes(entries, 3, rng);
    const from = fmtDate(entries[0].t);
    const to = fmtDate(entries[entries.length - 1].t);
    const lines = [];
    lines.push(`📊 群报（${from} - ${to}）`);
    lines.push(`💬 ${s.total} 条消息 · ${s.people} 个人${s.peakHour >= 0 ? ` · 最热闹 ${s.peakHour} 点` : ''}`);
    if (s.talkers.length > 0) {
        lines.push(`🗣 话痨榜：${s.talkers.map(([n, c]) => `${n} ${c}`).join('、')}`);
    }
    if (topics.length > 0) {
        lines.push(`🔥 热词：${topics.join('、')}`);
    }
    if (quotes.length > 0) {
        lines.push('✨ 名场面：');
        for (const q of quotes) lines.push(`「${q.text}」—— ${q.name}`);
    }
    else {
        lines.push('✨ 名场面：这周都在发表情，没留下什么能抄的金句');
    }
    return lines.join('\n');
}

/** 读记忆 → 出报告 */
export function buildReport({ days = 7, limit = 800 } = {}) {
    const mem = getMemoryStore();
    if (!mem) return { ok: false, reason: 'no-memory' };
    // 只有记录了一个群才能出报告；多群时取消息量最大的那个
    const groups = typeof mem.listPeers === 'function' ? mem.listPeers('group') : [];
    if (groups.length === 0) return { ok: false, reason: 'no-messages' };
    let best = null;
    for (const peerId of groups) {
        const since = Date.now() - days * 24 * 3600 * 1000;
        const entries = mem.readAll('group', peerId, since);
        if (!best || entries.length > best.entries.length) best = { peerId, entries };
    }
    if (!best || best.entries.length === 0) return { ok: false, reason: 'no-messages' };
    // 超长时只取后半段，保证发得出去
    let entries = best.entries;
    if (entries.length > limit) entries = entries.slice(-limit);
    const text = formatReport({ entries, days, topicsOf: (t) => mem.topicsOf(t) });
    return { ok: true, peerId: best.peerId, text, count: best.entries.length };
}
