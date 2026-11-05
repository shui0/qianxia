/**
 * 群聊回复策略闸门（二次加工新增）
 *
 * 目标：不 @ 也接话，但不是"每条都接"。
 *
 * 判定顺序（只作用于群聊；私聊永远放行）：
 *   1. 被 @                → 放行（原有的 mention 语义不变）
 *   2. 命中关键词          → 放行
 *   3. 冷却期内            → 丢弃（同一群刚接过话，先安静）
 *   4. 随机数 < probability → 放行，并记录本次时间
 *   5. 其余                → 丢弃（不创建会话、不调用模型、不烧 token）
 *
 * 被丢弃的消息已经由上游 historyBuffer 记进群上下文（middleware-setup 里
 * historyBuffer 排在门控之前、recordOnSkip: true），所以下次真正开口时
 * 它仍然"知道刚才大家在聊什么"。
 */
/** 每个群最后一次"随机接话"的时间戳 */
import { scheduleProactive } from "./proactive-talk.js";
import { isMenuRequest } from "./menu.js";
const lastAutoReplyAt = new Map();
function clamp01(n) {
    if (typeof n !== 'number' || Number.isNaN(n))
        return 0.2;
    return Math.min(1, Math.max(0, n));
}
/**
 * 创建回复策略中间件。
 * 注意：config.smartReply.enabled 为 false 时是完全透传（等价于原版行为）。
 */
export function createReplyPolicy(config, logger) {
    const opts = config.smartReply ?? {};
    const enabled = opts.enabled === true;
    const keywords = Array.isArray(opts.keywords)
        ? opts.keywords.filter((k) => typeof k === 'string' && k.trim().length > 0).map((k) => k.trim())
        : [];
    const probability = clamp01(opts.probability);
    const cooldownMs = Math.max(0, Number(opts.cooldownMs) || 0);
    const info = (m) => { try {
        logger?.info?.(m);
    }
    catch { /* 日志失败不影响主流程 */ } };
    const debug = (m) => { try {
        logger?.debug?.(m);
    }
    catch { /* 同上 */ } };
    return async function replyPolicy(ctx, next) {
        if (!enabled)
            return next();
        const msg = ctx?.message;
        if (!msg || msg.kind !== 'group')
            return next(); // 私聊不拦
        // 1. 被 @ 一定放行
        if (ctx.state?.mention?.wasMentioned === true)
            return next();
        const text = (msg.content ?? '').trim();
        // 1.5 要菜单：无条件放行（后面 inbound 会直接回菜单，不走模型）
        if (isMenuRequest(text)) {
            debug('im-qqbot[reply-policy]: 菜单请求 → 放行');
            return next();
        }
        // 2 关键词命中放行
        if (text.length > 0) {
            const hit = keywords.find((k) => text.includes(k));
            if (hit !== undefined) {
                debug(`im-qqbot[reply-policy]: 关键词命中「${hit}」→ 放行`);
                return next();
            }
        }
        const gid = msg.groupOpenid ?? msg.senderId ?? 'unknown';
        const now = Date.now();
        // 3. 冷却期：刚接过话就先安静
        const last = lastAutoReplyAt.get(gid) ?? 0;
        if (cooldownMs > 0 && now - last < cooldownMs) {
            debug(`im-qqbot[reply-policy]: 冷却中（还剩 ${Math.ceil((cooldownMs - (now - last)) / 1000)}s）→ 丢弃`);
            return undefined;
        }
        // 4. 随机接话
        if (Math.random() >= probability) {
            debug(`im-qqbot[reply-policy]: 未命中随机（p=${probability}）→ 丢弃`);
            return undefined;
        }
        lastAutoReplyAt.set(gid, now);
        // 不相关 + 没 @ → 排一次"过一会儿主动搭话"，而不是现在回这条
        const pt = config.proactiveTalk ?? {};
        if (pt.enabled === true) {
            const min = Math.max(0, Number(pt.minSec) || 0);
            const max = Math.max(min, Number(pt.maxSec) || 240);
            const delayMs = Math.round((min + Math.random() * (max - min)) * 1000);
            const r = scheduleProactive({ scope: 'group', peerId: gid, delayMs });
            info(`im-qqbot[reply-policy]: 排期搭话 ${Math.round(delayMs / 1000)}s 后（${r.ok ? 'ok' : r.reason}）group=${gid}`);
            return undefined;
        }
        // 没开搭话功能 → 退回原来的"直接接一句"
        if (ctx.state) ctx.state.proactive = true;
        info(`im-qqbot[reply-policy]: 随机接话（p=${probability}）group=${gid}`);
        return next();
    };
}
/** 测试/管理用：清空冷却状态 */
export function resetReplyPolicyState() {
    lastAutoReplyAt.clear();
}
/** 测试用：读取某群最后一次接话时间 */
export function getLastAutoReplyAt(groupId) {
    return lastAutoReplyAt.get(groupId);
}
