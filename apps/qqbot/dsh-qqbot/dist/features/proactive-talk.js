/**
 * 趁机搭话（二次加工新增）
 *
 * 场景：群里有人说话，但既没 @ 她、也没命中关键词 —— 这条消息本来是"不用理"的。
 * 这时按一个小概率，她不会立刻回，而是**排一个延迟**，到点后主动 @ 一个最近
 * 说过话的人，挑个过去聊过的话题开口。
 *
 * 为什么要延迟：秒回等于承认"我在盯着这个群"，延迟更像真人在忙别的。
 *
 * 硬约束（必须知道）：
 *   群聊的被动回复凭据（msgId）在插件里只缓存 5 分钟（msgid-cache TTL_GROUP）。
 *   超过这个窗口再发，就落到"主动推送"，而主动推送是每群每月 4 条。
 *   所以默认延迟上限压在 4 分钟；想赌服务器允许更长，可以调大 maxSec 实测。
 */
import { getCachedReplyIds } from "../transport/msgid-cache.js";
import { getMemoryStore } from "./memory-store.js";
import { createUserMessage } from '@deepseek-ai/dsh-llm';

let _deps = null;
const timers = new Map();

export function initProactiveTalk(deps) {
    _deps = deps;
    return _deps;
}

/** 取消某个群的待发搭话（有新消息进来时可以覆盖） */
export function cancelProactive(key) {
    const t = timers.get(key);
    if (t) {
        clearTimeout(t);
        timers.delete(key);
    }
}

/**
 * 排一次搭话。
 * @returns {{ok:boolean, reason?:string, delayMs?:number}}
 */
export function scheduleProactive({ scope, peerId, delayMs }) {
    if (!_deps) return { ok: false, reason: 'not-initialized' };
    const key = `${scope}:${peerId}`;
    if (timers.has(key)) return { ok: false, reason: 'already-scheduled' };
    // 目标消息必须在缓存有效期内，否则到点没有被动回复凭据
    const ids = getCachedReplyIds(scope, peerId);
    if (ids.length === 0) return { ok: false, reason: 'no-reply-target' };
    const timer = setTimeout(() => {
        timers.delete(key);
        void fire({ scope, peerId }).catch((err) => {
            _deps?.logger?.warn?.(`im-qqbot[proactive]: ${err instanceof Error ? err.message : String(err)}`);
        });
    }, Math.max(1000, delayMs));
    timers.set(key, timer);
    return { ok: true, delayMs };
}

/** 到点执行：挑人、组指令、驱动 agent 说一句 */
async function fire({ scope, peerId }) {
    const { manager, config, logger } = _deps ?? {};
    if (!manager || !config) return;
    const ids = getCachedReplyIds(scope, peerId);
    if (ids.length === 0) {
        logger?.info?.('im-qqbot[proactive]: 被动回复凭据已过期，放弃这次搭话');
        return;
    }
    const target = { scope, targetId: peerId, msgId: ids[0].id };

    // 候选：这个群最近说过话的人
    const mem = getMemoryStore();
    const recents = mem ? mem.recent(scope, peerId, 20) : [];
    const seen = new Map();
    for (const r of recents) {
        if (!r?.s) continue;
        if (!seen.has(r.s)) seen.set(r.s, r.n || String(r.s).slice(0, 8));
    }
    const candidates = [...seen.entries()].slice(-6); // [[openid, name]]
    if (candidates.length === 0) {
        logger?.info?.('im-qqbot[proactive]: 没有可 @ 的人，放弃');
        return;
    }

    // 话题：从群记忆里出现过的词挑几个
    const lines = recents.map((r) => r.c);
    const topics = mem && typeof mem.topicsOf === 'function' ? mem.topicsOf(lines) : [];

    const who = candidates.map(([id, n]) => `${n}(openid=${id})`).join('、');
    const instruction = [
        '[系统提示 · 这一轮不是你被叫到]',
        '群里刚才在聊天，但没人叫你。现在给你一个机会：主动找一个人搭话。',
        `可以 @ 的人：${who}`,
        topics.length > 0 ? `最近聊过的话题：${topics.join('、')}` : '',
        '要求：',
        '1. 只挑一个人，用一句话开口，别长篇大论。',
        '2. 想 @ 他就在句首写 [[at:对方的openid]]，系统会转成真的 @。',
        '3. 话题从上面那些里挑一个，或者顺着你记忆里的事问一句。',
        '4. 不要解释你在干嘛，不要说"我可以主动说话"这种。',
    ].filter(Boolean).join('\n');

    let record;
    try {
        record = await manager.getOrCreate(scope, peerId, 'proactive', target);
    } catch (err) {
        logger?.warn?.(`im-qqbot[proactive]: 取会话失败 ${err instanceof Error ? err.message : String(err)}`);
        return;
    }
    // 关键：把回复目标换成刚刚缓存里的那个 msgId，否则会走主动推送
    try { record.replyTarget = target; } catch { /* 忽略 */ }

    const message = createUserMessage({ content: [{ type: 'text', text: instruction }], source: { kind: 'user' } });
    record.agent.followup(message);
    logger?.info?.(`im-qqbot[proactive]: 已触发一次主动搭话 group=${peerId} 候选=${candidates.length}`);
}

/**
 * 把模型输出里的 [[at:openid]] 换成 QQ 的 @ 语法。
 * 注意：<qqbot-at-user> 只在 markdown 消息（msg_type=2）里生效，
 * 纯文本模式会原样显示，所以 config.mention.enabled=false 时这里直接剥掉标记。
 */
export function renderMentions(text, enabled) {
    if (typeof text !== 'string') return text;
    return text.replace(/\[\[at:([\w-]+)\]\]/g, (_m, id) => (enabled ? `<qqbot-at-user id="${id}" />` : '')).replace(/[ \t]{2,}/g, ' ').trim();
}
