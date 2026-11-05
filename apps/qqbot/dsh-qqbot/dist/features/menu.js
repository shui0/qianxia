/**
 * 功能菜单（二次加工新增）
 *
 * 群里 `@千夏` 不说话、或者说「菜单 / 功能 / 帮助」，直接甩一张功能列表。
 * 关键设计：**不经过模型**。这类交互是最频繁的入口，如果每次都调一轮 LLM，
 * 光"@一下看看有什么功能"就能烧掉不少 token，而且响应慢、还容易被问偏。
 * 固定文案 + 直接发送，零成本、秒回。
 */

export const MENU_TEXT = [
    '千夏会这些——',
    '',
    '🎲 骰子｜说「骰子 2d6」「掷骰子」',
    '🎯 抽人｜说「抽一个」或「谁去」',
    '🔢 猜数字｜说「猜数字」开局，之后直接说数字',
    '📊 周报｜说「周报」，看这周群里聊了啥',
    '📔 日记｜说「日记」看她写的东西',
    '💗 好感度｜说「好感度」，或问「你有多喜欢我」',
    '🖼 表情包｜说「表情包」发一张，「斗图」连发几张',
    '💬 闲聊｜随便说话，叫「千夏」就能叫醒她',
    '',
    '小提示：@千夏 或者叫名字都能唤醒。有时候不叫她，她也可能自己凑过来。',
].join('\n');

/** 是不是"只 @ 了她、什么都没说" */
export function isBareMention(msg, state) {
    if (!msg || msg.kind !== 'group') return false;
    const mentioned = state?.mention?.wasMentioned === true;
    if (!mentioned) return false;
    const text = String(msg.content ?? '').trim();
    return text.length === 0;
}

const MENU_WORDS = ['菜单', '功能', '帮助', 'help', 'help me', '你会什么', '你能做什么', '指令', '用法'];

/** 是不是在要菜单 */
export function isMenuRequest(text) {
    const t = String(text ?? '').trim().toLowerCase();
    if (!t) return false;
    // 太长的句子不算（"这个功能真好用"不该触发菜单）
    if (t.length > 12) return false;
    return MENU_WORDS.some((w) => t === w || t === `${w}?` || t === `${w}？` || t.startsWith(`${w} `));
}
