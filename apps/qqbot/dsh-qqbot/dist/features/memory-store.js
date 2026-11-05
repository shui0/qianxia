/**
 * 长期记忆（二次加工新增）
 *
 * 解决的问题：原插件的群历史只存在内存里，回复完就清空（clearGroupHistory），
 * 重启即失忆。这里把消息落到磁盘，并在每次组 prompt 时注入"最近聊了什么 +
 * 这个人的专属档案"。
 *
 * 目录结构（默认 <sticker 同级>/qq-memory）：
 *   qq-memory/messages/<scope>-<id>.jsonl   每个群/每个私聊一条 JSONL
 *   qq-memory/users/<openid>.json           每个用户一份专属档案
 *
 * 设计取舍：
 *   - 同步 fs：消息量小、单条追加，异步反而增加竞态。
 *   - 文件按 peer 切分，避免一个大文件越写越大还要做锁。
 *   - 话题提取用朴素 n-gram 频次（中文 2~3 字、英文 3 字以上），没有分词依赖，
 *     效果比"关键词表"糙，但零配置、能跑。
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, statSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';

const MAX_LINES_PER_FILE = 5000;
/** 好感度初始值：刚认识 */
const AFFINITY_START = 30;
/** 好感度等级（值 → 称呼） */
export function affinityLevel(v) {
    const n = Number(v) || 0;
    if (n < 20) return '有点陌生';
    if (n < 50) return '熟人';
    if (n < 100) return '朋友';
    if (n < 200) return '好朋友';
    if (n < 400) return '很喜欢';
    return '最喜欢';
}
/** 一句话里的情绪信号 → 好感度增减 */
export function affinityDelta(text, wasMentioned) {
    let d = 0.6;
    const t = String(text ?? '');
    if (/(可爱|厉害|好棒|太强|喜欢|爱你|牛|优秀|温柔|贴心|好看)/.test(t)) d += 2;
    if (/(笨蛋|讨厌|滚|闭嘴|烦人|恶心|垃圾)/.test(t)) d -= 1.2;
    if (wasMentioned) d += 1;
    return Math.max(-3, Math.min(3, d));
}
const RECENT_LIMIT = 20;
const PROFILE_TOPICS = 8;

/** 中文高频虚词/代词，做 2-gram 时会把它们切出一堆噪音 */
const STOP = new Set([
    '这个', '那个', '什么', '怎么', '可以', '我们', '你们', '他们', '就是', '还是', '不是',
    '没有', '知道', '觉得', '一下', '现在', '真的', '但是', '因为', '所以', '如果', '然后',
    '这样', '那样', '时候', '东西', '一个', '两个', '非常', '已经', '可能', '应该', '自己',
    '今天', '明天', '昨天', '现在', '还有', '有点', '一起', '不是', '这些', '那些', '感觉',
    '哈哈', '哈哈哈', '呵呵', '嗯嗯', '好的', '收到', '谢谢', '对不起', '没事',
]);

/**
 * 洗掉 QQ 的标记语言。记忆里存原始文本的话，周报、热词、日记、
 * 甚至她看到的上下文全都会被 <faceType=...>、<@xxx> 这种乱码污染。
 * 表情整段保留成 [表情]，其余标记直接删。
 */
export function cleanForMemory(text) {
    let t = String(text ?? '');
    if (!t) return '';
    // 纯表情 / 表情标签 → [表情]
    t = t.replace(/<faceType=[^>]*>/gi, '[表情]');
    // @ 别人 / @ 机器人
    t = t.replace(/<qqbot-at-user[^>]*>/gi, '');
    t = t.replace(/<@!?[0-9A-Za-z_-]+>/g, '');
    // CQ 码（老协议残留）
    t = t.replace(/\[CQ:[^\]]+\]/g, '');
    // 多余的尖括号残留标签
    t = t.replace(/<[a-zA-Z][^>]{0,60}>/g, '');
    t = t.replace(/\s+/g, ' ').trim();
    // 只剩一个 [表情] 时保持，多个压成一个
    t = t.replace(/(\[表情\]\s*){2,}/g, '[表情]');
    return t;
}

function safeName(s) {
    return String(s ?? 'unknown').replace(/[^\w.-]/g, '_').slice(0, 80);
}

export function createMemoryStore(rootDir, logger, opts = {}) {
    const root = resolve(rootDir);
    const RECENT = Math.max(3, Number(opts.recentLimit) || RECENT_LIMIT);
    const LINECAP = Math.max(30, Number(opts.lineChars) || 120);
    const msgDir = join(root, 'messages');
    const userDir = join(root, 'users');
    try {
        mkdirSync(msgDir, { recursive: true });
        mkdirSync(userDir, { recursive: true });
    }
    catch (e) {
        logger?.warn?.(`im-qqbot[memory]: 无法创建目录 ${root}: ${e?.message}`);
    }

    /** 取消息文件路径 */
    const msgPath = (scope, peerId) => join(msgDir, `${safeName(scope)}-${safeName(peerId)}.jsonl`);
    const userPath = (openid) => join(userDir, `${safeName(openid)}.json`);

    /** 追加一条消息（JSONL） */
    function record(entry) {
        const { scope, peerId, senderId, senderName, text, ts = Date.now() } = entry;
        if (!text || !peerId) return;
        const cleaned = cleanForMemory(text).slice(0, LINECAP);
        if (!cleaned) return;
        const line = JSON.stringify({ t: ts, s: senderId ?? '', n: senderName ?? '', c: cleaned });
        const p = msgPath(scope, peerId);
        try {
            appendFileSync(p, line + '\n', 'utf8');
            // 粗粒度截断：文件过大时轮转一次，避免无限增长
            if (statSync(p).size > 4 * 1024 * 1024) rotate(p);
        }
        catch (e) {
            logger?.warn?.(`im-qqbot[memory]: 写入失败 ${p}: ${e?.message}`);
        }
    }

    function rotate(p) {
        try {
            const lines = readFileSync(p, 'utf8').split('\n').filter(Boolean);
            writeFileSync(p, lines.slice(-MAX_LINES_PER_FILE).join('\n') + '\n', 'utf8');
        }
        catch { /* 截断失败就让它继续长，下次再试 */ }
    }

    /** 读最近 n 条 */
    function recent(scope, peerId, limit = RECENT) {
        const p = msgPath(scope, peerId);
        if (!existsSync(p)) return [];
        try {
            const lines = readFileSync(p, 'utf8').split('\n').filter(Boolean);
            return lines.slice(-limit).map((l) => {
                try {
                    const o = JSON.parse(l);
                    if (o && typeof o.c === 'string') o.c = cleanForMemory(o.c);
                    return o;
                }
                catch { return null; }
            }).filter(Boolean);
        }
        catch {
            return [];
        }
    }

    /** 读/写用户档案 */
    function readProfile(openid) {
        const p = userPath(openid);
        if (!existsSync(p)) return null;
        try {
            const o = JSON.parse(readFileSync(p, 'utf8'));
            if (o && Array.isArray(o.recentLines)) {
                o.recentLines = o.recentLines.map((l) => cleanForMemory(l)).filter(Boolean).slice(-20);
            }
            return o;
        }
        catch { return null; }
    }

    function writeProfile(openid, data) {
        const p = userPath(openid);
        try {
            const tmp = p + '.tmp';
            writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
            renameSync(tmp, p);
        }
        catch (e) {
            logger?.warn?.(`im-qqbot[memory]: 档案写入失败 ${p}: ${e?.message}`);
        }
    }

    /** 每次收到某人的消息就更新他的档案 */
    function touchUser({ openid, name, groupId, text, ts = Date.now() }) {
        if (!openid) return null;
        const prev = readProfile(openid) ?? {
            openid,
            name: name || '',
            firstSeen: ts,
            lastSeen: ts,
            messages: 0,
            groups: [],
            topicCounts: {},
            recentLines: [],
        };
        prev.name = name || prev.name;
        prev.lastSeen = ts;
        prev.messages = (prev.messages ?? 0) + 1;
        if (typeof prev.affinity !== 'number') prev.affinity = AFFINITY_START;
        if (groupId && !prev.groups.includes(groupId)) prev.groups = [...(prev.groups ?? []), groupId].slice(-10);
        if (text) {
            // 保留最近 20 句，话题从这 20 句里现算 —— 比"每条消息单独提词"稳：
            // 单条消息里「舞萌」只出现一次时，单独提取会被频次阈值滤掉，累计后就不会。
            prev.recentLines = [...(prev.recentLines ?? []), cleanForMemory(text).slice(0, 80)].slice(-20);
            prev.topics = extractTopics(prev.recentLines, 10);
        }
        prev.recentLines = (prev.recentLines ?? []).map((l) => cleanForMemory(l)).filter(Boolean).slice(-20);
        delete prev.topicCounts; // 老版本的字段，改用 topics
        writeProfile(openid, prev);
        return prev;
    }

    /**
     * 组装"长期记忆"块，拼在用户消息前面。
     * 返回空串表示没有可用记忆（比如第一次对话）。
     */
    function buildBlock({ scope, peerId, senderId, senderName, skipLast = false, currentText = '' }) {
        let recents = recent(scope, peerId, RECENT);
        // 当前这条已经被 memoryRecorder 记进去了，注入时去掉，免得同一句话出现两次
        if (skipLast && recents.length > 0) recents = recents.slice(0, -1);
        if (recents.length === 0) return '';
        const profile = senderId ? readProfile(senderId) : null;
        const lines = [];
        lines.push('[长期记忆 · 不用假装记得，但你确实看过这些]');
        lines.push(`群里最近 ${recents.length} 条：`);
        for (const r of recents) {
            const who = r.n || (r.s ? String(r.s).slice(0, 8) : '某人');
            lines.push(`- ${who}: ${String(r.c).replace(/\s+/g, ' ').slice(0, LINECAP)}`);
        }
        if (profile) {
            const topics = (profile.topics ?? []).slice(0, PROFILE_TOPICS).join('、');
            lines.push('');
            const aff = Number(profile.affinity) || AFFINITY_START;
            lines.push(`[当前说话人档案] ${profile.name || senderName || '这位'}｜好感 ${aff.toFixed(0)}（${affinityLevel(aff)}）｜见面 ${profile.messages} 次｜常聊：${topics || '（还不多）'}`);
            const cur = cleanForMemory(currentText);
            const priorLines = (profile.recentLines ?? [])
                .filter((l) => !cur || l !== cur)
                .slice(-3);
            if (priorLines.length > 0) {
                lines.push(`他之前说过：${priorLines.join(' / ')}`);
            }
        }
        lines.push('[长期记忆结束]');
        return lines.join('\n') + '\n\n';
    }

    /** 加好感（静默失败，不阻断消息） */
    function bumpAffinity(openid, delta) {
        if (!openid || !delta) return null;
        const p = readProfile(openid);
        if (!p) return null;
        const next = Math.max(0, Math.min(999, (Number(p.affinity) || AFFINITY_START) + delta));
        p.affinity = Math.round(next * 10) / 10;
        writeProfile(openid, p);
        return p.affinity;
    }
    /** 所有档案的 openid 列表 */
    function listUsers() {
        try {
            return readdirSync(userDir).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5));
        }
        catch {
            return [];
        }
    }
    /** 按名字找人（重名取好感最高的） */
    function findUserByName(name) {
        const q = String(name ?? '').trim();
        if (!q) return null;
        let best = null;
        for (const id of listUsers()) {
            const p = readProfile(id);
            if (!p) continue;
            if (p.name === q || (p.name && p.name.includes(q))) {
                if (!best || (p.affinity ?? 0) > (best.affinity ?? 0)) best = p;
            }
        }
        return best;
    }
    /** 读某 peer 的全部消息（可按时间过滤），周报用 */
    function readAll(scope, peerId, sinceTs = 0) {
        const p = msgPath(scope, peerId);
        if (!existsSync(p)) return [];
        try {
            return readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => {
                try {
                    const o = JSON.parse(l);
                    if (o && typeof o.c === 'string') o.c = cleanForMemory(o.c);
                    return o;
                }
                catch { return null; }
            }).filter((x) => x && x.c && (sinceTs <= 0 || Number(x.t) >= sinceTs));
        }
        catch {
            return [];
        }
    }
    /** 列出记录过的 peer（文件名里解析），周报用 */
    function listPeers(scope) {
        try {
            return readdirSync(msgDir)
                .filter((f) => f.startsWith(`${safeName(scope)}-`) && f.endsWith('.jsonl'))
                .map((f) => f.slice(safeName(scope).length + 1, -'.jsonl'.length));
        }
        catch {
            return [];
        }
    }
    /** 给"主动搭话"用：从一组消息里提话题 */
    const topicsOf = (lines) => extractTopics(lines, 6);
    return { record, recent, readAll, listPeers, touchUser, bumpAffinity, listUsers, findUserByName, buildBlock, readProfile, topicsOf, cleanForMemory, root };
}

let _store = null;

/** 由 bootstrap 初始化（rootDir 为空则关闭长期记忆） */
export function initMemoryStore(rootDir, logger, opts = {}) {
    _store = rootDir ? createMemoryStore(rootDir, logger, opts) : null;
    if (_store) logger?.info?.(`im-qqbot[memory]: 长期记忆已启用 → ${_store.root}`);
    else logger?.info?.('im-qqbot[memory]: 长期记忆未启用');
    return _store;
}

/** 取当前实例（未初始化时为 null） */
export function getMemoryStore() {
    return _store;
}

/**
 * 记忆记录中间件：挂在 historyBuffer 之后、所有门控之前。
 * 位置很重要——gate（@门控、回复策略）之前的消息也要记，
 * 否则"她没理的那些话"永远进不了长期记忆。
 */
export function createMemoryRecorder(config, logger) {
    return async function memoryRecorder(ctx, next) {
        try {
            const mem = getMemoryStore();
            const msg = ctx?.message;
            if (mem && msg) {
                const scope = msg.kind === 'group' ? 'group' : 'c2c';
                const peerId = scope === 'group' ? (msg.groupOpenid ?? msg.senderId) : msg.senderId;
                const text = (msg.content ?? '').trim();
                if (text && peerId) {
                    mem.record({ scope, peerId, senderId: msg.senderId, senderName: msg.senderName, text });
                    mem.touchUser({
                        openid: msg.senderId,
                        name: msg.senderName,
                        groupId: scope === 'group' ? peerId : undefined,
                        text,
                    });
                    // 好感度：每句话都在悄悄变（见 affinityDelta）
                    mem.bumpAffinity(msg.senderId, affinityDelta(text, ctx?.state?.mention?.wasMentioned === true));
                }
            }
        }
        catch (err) {
            logger?.warn?.(`im-qqbot[memory]: 记录失败 ${err instanceof Error ? err.message : String(err)}`);
        }
        return next();
    };
}

/**
 * 朴素话题提取：中文取 2~3 字连续片段，英文取 3 字以上单词，按 频次×长度 排序。
 * 没有分词，会把「吃了吗」切成「吃了」「了吗」这种，但高频词仍然会浮上来。
 */
export function extractTopics(texts, limit = 5) {
    const counts = new Map();
    const bump = (k) => {
        if (!k || STOP.has(k)) return;
        counts.set(k, (counts.get(k) ?? 0) + 1);
    };
    for (const raw of texts ?? []) {
        const text = String(raw ?? '').replace(/https?:\/\/\S+/g, ' ');
        for (const run of text.match(/[\u4e00-\u9fa5]{2,}/g) ?? []) {
            for (let n = 2; n <= 3; n++) {
                for (let i = 0; i + n <= run.length; i++) bump(run.slice(i, i + n));
            }
        }
        for (const w of text.match(/[a-zA-Z]{3,}/g) ?? []) bump(w.toLowerCase());
    }
    // 去掉"是别人子串且频次不更高"的碎片
    const entries = [...counts.entries()].sort((a, b) => b[1] * b[0].length - a[1] * a[0].length);
    const out = [];
    for (const [k, v] of entries) {
        if (v < 2) continue;
        // 已经被更长的词覆盖就跳过
        if (out.some((o) => o.includes(k) || k.includes(o))) continue;
        // 和已选的词有 2 字重叠 → 拼成更长的词（公司电 + 司电脑 = 公司电脑）
        let merged = null;
        for (let i = 0; i < out.length; i += 1) {
            const o = out[i];
            if (o.slice(-2) === k.slice(0, 2) && !o.includes(k)) { merged = o + k.slice(2); out[i] = merged; break; }
            if (k.slice(-2) === o.slice(0, 2) && !k.includes(o)) { merged = k + o.slice(2); out[i] = merged; break; }
        }
        if (merged !== null) {
            // 拼接后可能和别的重复，去重一次
            const uniq = [];
            for (const x of out) if (!uniq.some((u) => u.includes(x) || x.includes(u))) uniq.push(x);
            out.length = 0;
            out.push(...uniq);
            if (out.length >= limit) break;
            continue;
        }
        out.push(k);
        if (out.length >= limit) break;
    }
    return out;
}
