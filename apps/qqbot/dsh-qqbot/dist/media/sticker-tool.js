/**
 * 内置 qqbot_send_sticker 工具（二次加工新增）
 *
 * 让模型从本地表情包库里"搜一张合适的"并发到当前会话。
 *
 *   - 库目录：config.sticker.dir（默认 <cwd>/stickers），递归扫描图片。
 *   - 标签来源：文件名（去掉扩展名）+ 所有上级目录名，按空格/下划线/短横线切词。
 *   - 搜索：query 与标签做大小写不敏感的子串匹配，打分取最高的一组，随机挑一张。
 *   - 兜底：query 为空或没命中 → 随机一张（不会因为"找不到"就什么都不发）。
 *
 * 为什么是本地库而不是在线搜图：在线图源要么要 key、要么是抓取，且图片版权
 * 与可用性都不稳；本地库是可控的（你自己往里丢图就能用），离线也能跑。
 */
import { readdirSync, statSync } from 'node:fs';
import { basename, extname, join, resolve } from 'node:path';
import { sendMediaFile } from "./send-media.js";
export const SEND_STICKER_TOOL_NAME = 'qqbot_send_sticker';
const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']);
const MAX_SCAN_DEPTH = 4;
const MAX_LIBRARY = 5000;
/** query 里的分隔符切成词元 */
function tokenize(s) {
    return s
        .toLowerCase()
        .split(/[\s_\-.,，。、/\\]+/)
        .map((t) => t.trim())
        .filter((t) => t.length > 0);
}
/** 递归收集表情包文件，返回 { path, name, tags, top } */
export function scanLibrary(root) {
    const out = [];
    const walk = (dir, depth, dirTags, top) => {
        if (depth > MAX_SCAN_DEPTH || out.length >= MAX_LIBRARY)
            return;
        let entries;
        try {
            entries = readdirSync(dir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const entry of entries) {
            if (out.length >= MAX_LIBRARY)
                return;
            // 以 _ 或 . 开头的目录/文件不参与扫描（用来"雪藏"某批图）
            if (entry.name.startsWith('_') || entry.name.startsWith('.'))
                continue;
            const full = join(dir, entry.name);
            if (entry.isDirectory()) {
                const nextTop = top ?? entry.name;
                walk(full, depth + 1, [...dirTags, ...tokenize(entry.name)], nextTop);
                continue;
            }
            if (!entry.isFile())
                continue;
            const ext = extname(entry.name).toLowerCase();
            if (!IMAGE_EXTS.has(ext))
                continue;
            const stem = basename(entry.name, extname(entry.name));
            const tags = [...dirTags, ...tokenize(stem)];
            out.push({ path: full, name: entry.name, tags: [...new Set(tags)], top: top ?? '' });
        }
    };
    walk(root, 0, [], undefined);
    return out;
}
/** 打分：完全相等的标签 3 分，包含关系 2 分，query 词元部分命中 1 分 */
function score(sticker, queryTokens) {
    if (queryTokens.length === 0)
        return 0;
    let total = 0;
    for (const q of queryTokens) {
        for (const tag of sticker.tags) {
            if (tag === q) {
                total += 3;
            }
            else if (tag.includes(q) || q.includes(tag)) {
                total += 2;
            }
            else if (tag.startsWith(q.slice(0, 2)) && q.length >= 2) {
                total += 1;
            }
        }
    }
    return total;
}
/**
 * 在库里搜一张：返回 { pick, candidates, total }
 *
 * options.prefer：优先目录（顶层目录名数组）。
 *   - 命中查询时，优先目录里的图额外 +3 分（平分时才赢，不会盖过词义）；
 *   - 没命中、或需要随机兜底时，只从优先目录里抽。
 *   这样"尽量用这批、别用那批"就成立，又不会让搜不准的图抢占语义匹配。
 */
export function search(library, query, options = {}) {
    const qTokens = tokenize(query ?? '');
    const prefer = new Set((options.prefer ?? []).filter(Boolean));
    const preferredPool = prefer.size > 0 ? library.filter((s) => prefer.has(s.top)) : library;
    const pool = preferredPool.length > 0 ? preferredPool : library;
    if (library.length === 0)
        return { pick: undefined, candidates: [], total: 0 };
    const randomFrom = (list) => list[Math.floor(Math.random() * list.length)];
    if (qTokens.length === 0) {
        return { pick: randomFrom(pool), candidates: [], total: library.length };
    }
    const scored = library
        .map((s) => {
            const base = score(s, qTokens);
            const bonus = base > 0 && prefer.has(s.top) ? 3 : 0;
            return { s, v: base + bonus };
        })
        .filter((x) => x.v > 0)
        .sort((a, b) => b.v - a.v);
    if (scored.length === 0) {
        // 没有任何语义命中 → 从优先目录里随机（而不是从"不想用"的那批里挑）
        return { pick: randomFrom(pool), candidates: [], total: library.length };
    }
    const best = scored[0].v;
    const top = scored.filter((x) => x.v === best).map((x) => x.s);
    return { pick: randomFrom(top), candidates: scored.slice(0, 8).map((x) => x.s.name), total: library.length };
}
export function registerStickerTool(ctx, mediaSender, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_send_sticker 工具未注册');
        return;
    }
    const cwd = config.cwd || process.cwd();
    const root = resolve(config.sticker?.dir || join(cwd, 'stickers'));
    logger.info(`im-qqbot: 表情包库目录 ${root}（启用=${config.sticker?.enabled === true}）`);
    const definition = {
        name: SEND_STICKER_TOOL_NAME,
        description: 'Send a meme/sticker image from the local sticker library to the current QQ conversation. '
            + 'Search by mood or keyword (e.g. "开心", "无语", "抱抱", "好耶"). '
            + 'If nothing matches, a random sticker is sent instead. '
            + 'Set "preview": true to only list candidates without sending.',
        parameters: {
            type: 'object',
            properties: {
                query: {
                    type: 'string',
                    description: 'Keyword or mood to search for. Empty string = random sticker.',
                },
                preview: {
                    type: 'boolean',
                    description: 'When true, only returns candidate file names without sending anything.',
                },
                target: {
                    type: 'string',
                    description: 'Optional send target as "c2c:openid" or "group:openid". Omit for the current conversation.',
                },
            },
            required: [],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: {
                    sent: { type: 'boolean' },
                    fileName: { type: 'string' },
                    matched: { type: 'integer' },
                    total: { type: 'integer' },
                    candidates: { type: 'array', items: { type: 'string' } },
                },
                required: ['sent', 'total'],
                additionalProperties: false,
            },
            render: (_args, value) => {
                const v = value;
                if (!v.sent)
                    return [{ type: 'text', text: `表情包库共 ${v.total} 张，候选：${(v.candidates ?? []).join('、') || '（无）'}` }];
                return [{ type: 'text', text: `已发送表情包 ${v.fileName ?? ''}` }];
            },
        },
        async execute(args, exec) {
            if (config.sticker?.enabled !== true) {
                throw new Error('qqbot_send_sticker: 表情包功能未启用（config.sticker.enabled = false）');
            }
            let stat = undefined;
            try {
                stat = statSync(root);
            }
            catch {
                throw new Error(`qqbot_send_sticker: 表情包库目录不存在: ${root}`);
            }
            if (!stat.isDirectory()) {
                throw new Error(`qqbot_send_sticker: 不是目录: ${root}`);
            }
            const library = scanLibrary(root);
            const { pick, candidates, total } = search(library, args.query, { prefer: config.sticker?.prefer ?? [] });
            if (args.preview === true || pick === undefined) {
                // 预览时把"本来会发的那张"也列进候选，否则随机兜底看起来像"什么都没找到"
                const shown = pick !== undefined ? [pick.name, ...candidates.filter((n) => n !== pick.name)].slice(0, 8) : candidates;
                return { sent: false, total, candidates: shown };
            }
            // 解析发送目标：显式 target > 当前会话
            let replyTarget;
            if (typeof args.target === 'string' && args.target.length > 0) {
                const idx = args.target.indexOf(':');
                const scope = args.target.slice(0, idx);
                const targetId = args.target.slice(idx + 1);
                if (idx <= 0 || (scope !== 'c2c' && scope !== 'group') || !targetId) {
                    throw new Error(`qqbot_send_sticker: target 格式错误，需要 c2c:openid 或 group:openid，收到: ${args.target}`);
                }
                replyTarget = { scope, targetId };
            }
            else if (exec.agent !== undefined) {
                replyTarget = manager.findByAgent(exec.agent)?.replyTarget;
            }
            if (replyTarget === undefined) {
                throw new Error('qqbot_send_sticker: 无法确定发送目标，请显式传 target');
            }
            const result = await sendMediaFile(mediaSender, replyTarget, pick.path);
            if (result.outcome === 'missing') {
                throw new Error(`qqbot_send_sticker: 文件不可读: ${pick.path}`);
            }
            if (result.outcome === 'failed') {
                throw new Error(`qqbot_send_sticker: 发送失败: ${result.error}`);
            }
            logger.info(`im-qqbot: 发送表情包 ${pick.name} → ${replyTarget.scope}:${replyTarget.targetId}`);
            return {
                sent: true,
                fileName: pick.name,
                matched: candidates.length,
                total,
                candidates,
            };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_send_sticker 工具已注册');
}
