/**
 * 千夏的日记（二次加工新增）
 *
 * 她想写的时候写一条，存在本地。之后能翻看，也能当闲聊素材。
 * 之所以不做成"每天定时自动写"：定时主动发消息要吃每月 4 条的配额，
 * 而写日记本身不需要发言权 —— 让她在"有人在的时候"顺手写完就行。
 *
 * 目录：<memory>/diary/<peerId>.jsonl，一行一条 {t, date, text}
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { getMemoryStore } from './memory-store.js';

const MAX_CHARS = 400;

function safeName(s) {
    return String(s ?? 'unknown').replace(/[^\w.-]/g, '_').slice(0, 80);
}

function diaryPath(peerId) {
    const mem = getMemoryStore();
    const root = mem?.root ?? resolve(process.cwd(), 'qq-memory');
    const dir = join(root, 'diary');
    try { mkdirSync(dir, { recursive: true }); } catch { /* ignore */ }
    return join(dir, `${safeName(peerId)}.jsonl`);
}

function today() {
    const d = new Date();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
}

/** 写一条日记。text 为空时拒绝，避免写空条目。 */
export function writeDiary(peerId, text, ts = Date.now()) {
    const t = String(text ?? '').trim().slice(0, MAX_CHARS);
    if (!t) return { ok: false, reason: 'empty' };
    const row = JSON.stringify({ t: ts, date: today(), text: t });
    try {
        appendFileSync(diaryPath(peerId), row + '\n', 'utf8');
        return { ok: true, date: today() };
    }
    catch (e) {
        return { ok: false, reason: e instanceof Error ? e.message : String(e) };
    }
}

/** 读最近 n 条（新的在前） */
export function readDiary(peerId, limit = 3) {
    const p = diaryPath(peerId);
    if (!existsSync(p)) return [];
    try {
        return readFileSync(p, 'utf8').split('\n').filter(Boolean)
            .map((l) => { try { return JSON.parse(l); } catch { return null; } })
            .filter(Boolean)
            .slice(-limit)
            .reverse();
    }
    catch {
        return [];
    }
}

/**
 * 给日记准备"素材"：今天群里聊了谁、聊了什么、有哪句好玩的话。
 * 这是给模型看的原料，不是成品日记。
 */
export function diaryMaterial(peerId, dayTs = Date.now()) {
    const mem = getMemoryStore();
    if (!mem) return null;
    const start = new Date(dayTs);
    start.setHours(0, 0, 0, 0);
    const entries = mem.readAll('group', peerId, start.getTime());
    if (entries.length === 0) return { empty: true, count: 0 };
    const people = new Map();
    for (const e of entries) {
        const n = e.n || (e.s ? String(e.s).slice(0, 8) : '某人');
        people.set(n, (people.get(n) ?? 0) + 1);
    }
    const topics = mem.topicsOf(entries.map((e) => e.c)) ?? [];
    const quotes = entries
        .map((e) => ({ t: String(e.c ?? '').trim(), n: e.n || '某人' }))
        .filter((q) => q.t.length >= 8 && q.t.length <= 40)
        .slice(-40);
    // 随机挑两条当"素材"，别每次都一样
    const picked = [];
    while (picked.length < 2 && quotes.length > 0) {
        picked.push(quotes.splice(Math.floor(Math.random() * quotes.length), 1)[0]);
    }
    return {
        empty: false,
        count: entries.length,
        people: [...people.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4),
        topics,
        quotes: picked,
    };
}
