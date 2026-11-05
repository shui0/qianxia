/**
 * 小游戏（二次加工新增）
 *
 * 三个纯文本玩法，不依赖任何外部服务：
 *   dice        掷骰子（支持 3d6+2 这种表达式）
 *   draw        从一群人里抽一个（点外卖、谁去买奶茶）
 *   guess       猜数字：她心里想 1~100，群里猜，她说大了小了
 *
 * 猜数字的状态存在 games.json 里，按群隔离；重启后还在。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { getMemoryStore } from './memory-store.js';

const MAX_DICE = 20;   // 一次最多 20 颗，防滥用
const MAX_SIDES = 1000;
const GUESS_LOW = 1;
const GUESS_HIGH = 100;
const GUESS_MAX_TRIES = 20;

function gamesPath() {
    const mem = getMemoryStore();
    const root = mem?.root ?? resolve(process.cwd(), 'qq-memory');
    try { mkdirSync(root, { recursive: true }); } catch { /* ignore */ }
    return join(root, 'games.json');
}

function loadGames() {
    const p = gamesPath();
    if (!existsSync(p)) return {};
    try { return JSON.parse(readFileSync(p, 'utf8')) ?? {}; } catch { return {}; }
}

function saveGames(games) {
    const p = gamesPath();
    try {
        const tmp = p + '.tmp';
        writeFileSync(tmp, JSON.stringify(games, null, 2), 'utf8');
        renameSync(tmp, p);
    }
    catch { /* 存不下就算了，不阻断聊天 */ }
}

/**
 * 掷骰子。表达式：`2d6`、`d20`、`3d8+2`、`1d100-5`
 * 返回 { ok, rolls, total } 或 { ok:false, reason }
 */
export function rollDice(expr, rng = Math.random) {
    const m = String(expr ?? '').trim().toLowerCase().match(/^(\d*)d(\d+)([+-]\d+)?$/);
    if (!m) return { ok: false, reason: 'bad-format' };
    const count = m[1] === '' ? 1 : Number(m[1]);
    const sides = Number(m[2]);
    const mod = m[3] ? Number(m[3]) : 0;
    if (!Number.isFinite(count) || count < 1 || count > MAX_DICE) return { ok: false, reason: 'too-many-dice' };
    if (!Number.isFinite(sides) || sides < 2 || sides > MAX_SIDES) return { ok: false, reason: 'bad-sides' };
    const rolls = [];
    for (let i = 0; i < count; i++) rolls.push(1 + Math.floor(rng() * sides));
    const total = rolls.reduce((a, b) => a + b, 0) + mod;
    return { ok: true, rolls, total, mod, sides, count };
}

/** 从人群里抽一个（去重、去空） */
export function drawOne(candidates, rng = Math.random) {
    const list = [...new Set((candidates ?? []).map((s) => String(s ?? '').trim()).filter(Boolean))];
    if (list.length === 0) return { ok: false, reason: 'empty' };
    return { ok: true, pick: list[Math.floor(rng() * list.length)], total: list.length };
}

/** 开始一局猜数字 */
export function startGuess(peerId, rng = Math.random) {
    const games = loadGames();
    const target = GUESS_LOW + Math.floor(rng() * (GUESS_HIGH - GUESS_LOW + 1));
    games[`guess:${peerId}`] = { target, tries: 0, startedAt: Date.now() };
    saveGames(games);
    return { ok: true, range: [GUESS_LOW, GUESS_HIGH] };
}

/** 猜一次 */
export function tryGuess(peerId, n) {
    const games = loadGames();
    const key = `guess:${peerId}`;
    const g = games[key];
    if (!g) return { ok: false, reason: 'not-started' };
    const num = Number(n);
    if (!Number.isInteger(num) || num < GUESS_LOW || num > GUESS_HIGH) return { ok: false, reason: 'out-of-range' };
    g.tries += 1;
    let result;
    if (num === g.target) {
        result = 'win';
        const tries = g.tries;
        delete games[key];
        saveGames(games);
        return { ok: true, result, tries };
    }
    result = num > g.target ? 'high' : 'low';
    if (g.tries >= GUESS_MAX_TRIES) {
        const target = g.target;
        delete games[key];
        saveGames(games);
        return { ok: true, result: 'gaveup', tries: g.tries, target };
    }
    saveGames(games);
    return { ok: true, result, tries: g.tries };
}

/** 看当前局（不猜） */
export function guessState(peerId) {
    const g = loadGames()[`guess:${peerId}`];
    return g ? { ok: true, tries: g.tries } : { ok: false, reason: 'not-started' };
}

/** 结束当前局，返回答案 */
export function stopGuess(peerId) {
    const games = loadGames();
    const key = `guess:${peerId}`;
    const g = games[key];
    if (!g) return { ok: false, reason: 'not-started' };
    delete games[key];
    saveGames(games);
    return { ok: true, target: g.target, tries: g.tries };
}
