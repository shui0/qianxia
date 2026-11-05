/**
 * 情绪状态机（二次加工新增）
 *
 * 两个维度：
 *   energy 元气 0~100 —— 主要由**时间**决定（凌晨当然困），会随时间往基准值回落
 *   mood   心情 0~100 —— 主要由**互动**决定（被夸上升、被凶下降）
 *
 * 两者合成一个标签，塞进记忆块，让她说话的语气跟着变：
 *   凌晨被叫醒 → 「唔……几点了……」
 *   被夸了半天 → 「诶嘿！千夏今天超厉害的！」
 *
 * 按群隔离（不同群的人看到的状态不一样），存 qq-memory/mood.json。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { getMemoryStore } from './memory-store.js';

/** 各时段的基础元气值（小时 → 0~100） */
const ENERGY_BASE = [
    [0, 12], [5, 10], [7, 45], [9, 80], [12, 85],
    [14, 50], [16, 75], [19, 82], [22, 60], [24, 20],
];

function moodPath() {
    const mem = getMemoryStore();
    const root = mem?.root ?? resolve(process.cwd(), 'qq-memory');
    try { mkdirSync(root, { recursive: true }); } catch { /* ignore */ }
    return join(root, 'mood.json');
}

function loadAll() {
    const p = moodPath();
    if (!existsSync(p)) return {};
    try { return JSON.parse(readFileSync(p, 'utf8')) ?? {}; } catch { return {}; }
}

function saveAll(all) {
    const p = moodPath();
    try {
        const tmp = p + '.tmp';
        writeFileSync(tmp, JSON.stringify(all, null, 2), 'utf8');
        renameSync(tmp, p);
    }
    catch { /* 存不下不阻断聊天 */ }
}

/** 按小时插值出基础元气 */
export function baseEnergy(hour) {
    const h = ((hour % 24) + 24) % 24;
    for (let i = 0; i < ENERGY_BASE.length - 1; i += 1) {
        const [h0, v0] = ENERGY_BASE[i];
        const [h1, v1] = ENERGY_BASE[i + 1];
        if (h >= h0 && h < h1) {
            const t = (h - h0) / (h1 - h0);
            return Math.round(v0 + (v1 - v0) * t);
        }
    }
    return 40;
}

/** 距离上次更新过了一段时间 → 元气往基准靠，心情慢慢回到中性 */
export function drift(state, nowMs = Date.now()) {
    const base = baseEnergy(new Date(nowMs).getHours());
    const hours = Math.max(0, (nowMs - (state.updatedAt ?? nowMs)) / 3600000);
    // 每小时把差距缩小 60%，最多 6 小时收敛完
    const k = 1 - Math.pow(0.4, Math.min(hours, 6));
    const energy = (state.energy ?? base) + (base - (state.energy ?? base)) * k;
    const mood = (state.mood ?? 60) + (60 - (state.mood ?? 60)) * k * 0.5;
    return { energy, mood, updatedAt: nowMs };
}

/** 事件对心情/元气的影响 */
export function applyEvent(state, event, nowMs = Date.now()) {
    const s = drift(state, nowMs);
    switch (event) {
        case 'praise': s.mood += 8; s.energy += 4; break;
        case 'insult': s.mood -= 10; break;
        case 'chat': s.mood += 0.8; break;
        case 'sticker': s.mood += 2; s.energy += 2; break;
        case 'game': s.mood += 5; s.energy += 3; break;
        case 'ignored': s.mood -= 1.5; break;
        default: break;
    }
    s.energy = Math.max(0, Math.min(100, s.energy));
    s.mood = Math.max(0, Math.min(100, s.mood));
    s.updatedAt = nowMs;
    return s;
}

/** 合成标签 */
export function moodLabel(state) {
    const e = state?.energy ?? 50;
    const m = state?.mood ?? 60;
    if (e < 22) return { key: 'sleepy', text: '困得不行' };
    if (m < 28) return { key: 'down', text: '有点蔫' };
    if (m > 82 && e > 55) return { key: 'hyper', text: '超兴奋' };
    if (e < 45) return { key: 'tired', text: '有点累' };
    if (m > 65) return { key: 'happy', text: '心情不错' };
    return { key: 'calm', text: '平静' };
}

/** 读当前状态（会先做时间漂移，不落盘） */
export function peekMood(peerId, nowMs = Date.now()) {
    const all = loadAll();
    const raw = all[`mood:${peerId}`] ?? { energy: baseEnergy(new Date(nowMs).getHours()), mood: 60, updatedAt: nowMs };
    return drift(raw, nowMs);
}

/** 记一次事件并落盘 */
export function bumpMood(peerId, event, nowMs = Date.now()) {
    const all = loadAll();
    const key = `mood:${peerId}`;
    const raw = all[key] ?? { energy: baseEnergy(new Date(nowMs).getHours()), mood: 60, updatedAt: nowMs };
    const next = applyEvent(raw, event, nowMs);
    all[key] = next;
    saveAll(all);
    return next;
}

/** 给提示词用的一行状态 */
export function moodLine(peerId, nowMs = Date.now()) {
    const s = peekMood(peerId, nowMs);
    const label = moodLabel(s);
    return `千夏现在：${label.text}（元气 ${Math.round(s.energy)} / 心情 ${Math.round(s.mood)}）`;
}
