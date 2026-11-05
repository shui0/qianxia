/**
 * qqbot_minigame 工具（二次加工新增）
 *
 * 一个工具带三种玩法，靠 action 区分。她只在被叫到时调，不主动开团。
 */
import { rollDice, drawOne, startGuess, tryGuess, stopGuess, guessState } from './minigame.js';
import { getMemoryStore } from './memory-store.js';

export const MINIGAME_TOOL_NAME = 'qqbot_minigame';

export function registerMinigameTool(ctx, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_minigame 工具未注册');
        return;
    }
    const definition = {
        name: MINIGAME_TOOL_NAME,
        description: 'Play a tiny text game in the group. actions: '
            + '"dice" rolls dice (dice:"2d6"), "draw" picks one person from a list (from:["a","b"]), '
            + '"guess-start" starts a 1-100 guessing game, "guess-try" guesses a number (number:42), '
            + '"guess-stop" reveals the answer. '
            + 'Use when someone says 掷骰子 / 抽签 / 谁去 / 猜数字.',
        parameters: {
            type: 'object',
            properties: {
                action: {
                    type: 'string',
                    enum: ['dice', 'draw', 'guess-start', 'guess-try', 'guess-stop'],
                    description: 'Which game action to run.',
                },
                dice: { type: 'string', description: 'Dice expression for action=dice, e.g. "2d6" or "d20+3". Defaults to "1d6".' },
                from: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Candidate names for action=draw. Omit to draw from people who talked recently.',
                },
                number: { type: 'integer', description: 'The guessed number for action=guess-try.' },
            },
            required: ['action'],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: {
                    ok: { type: 'boolean' },
                    text: { type: 'string' },
                },
                required: ['ok', 'text'],
                additionalProperties: false,
            },
            render: (_a, v) => [{ type: 'text', text: v.text }],
        },
        execute(args, exec) {
            const peerId = manager.findByAgent(exec.agent)?.replyTarget?.targetId ?? 'unknown';
            const action = args.action;
            if (action === 'dice') {
                const expr = typeof args.dice === 'string' && args.dice.trim() ? args.dice.trim() : '1d6';
                const r = rollDice(expr);
                if (!r.ok) return { ok: false, text: `这个骰子千夏看不懂：${expr}` };
                const detail = r.count > 1 ? `${r.rolls.join(' + ')}${r.mod ? (r.mod > 0 ? ` + ${r.mod}` : ` - ${Math.abs(r.mod)}`) : ''}` : '';
                return { ok: true, text: `🎲 ${expr} = **${r.total}**${detail ? `（${detail}）` : ''}` };
            }
            if (action === 'draw') {
                let pool = Array.isArray(args.from) ? args.from : [];
                if (pool.length === 0) {
                    const mem = getMemoryStore();
                    const recents = mem ? mem.recent('group', peerId, 30) : [];
                    pool = [...new Set(recents.map((r) => r.n).filter(Boolean))];
                }
                const r = drawOne(pool);
                if (!r.ok) return { ok: false, text: '没人可以抽诶，先几个人说句话吧' };
                return { ok: true, text: `🎯 抽到 **${r.pick}** 了！（${r.total} 个人里）` };
            }
            if (action === 'guess-start') {
                const r = startGuess(peerId);
                return { ok: true, text: `千夏想好了一个 ${r.range[0]}~${r.range[1]} 之间的数，来猜！` };
            }
            if (action === 'guess-try') {
                const r = tryGuess(peerId, args.number);
                if (!r.ok) {
                    return {
                        ok: false,
                        text: r.reason === 'not-started' ? '现在没有在猜数字哦，要先说「猜数字」开一局' : '这个数不在 1~100 里啦',
                    };
                }
                if (r.result === 'win') return { ok: true, text: `对啦！！就是 ${args.number}，猜了 ${r.tries} 次！` };
                if (r.result === 'gaveup') return { ok: true, text: `猜了 ${r.tries} 次还没中，答案是 ${r.target}，下次再来~` };
                return { ok: true, text: `${args.number} ${r.result === 'high' ? '大了' : '小了'}（第 ${r.tries} 次）` };
            }
            // guess-stop
            const s = stopGuess(peerId);
            if (!s.ok) return { ok: false, text: '现在没在猜数字' };
            return { ok: true, text: `答案是 ${s.target}，猜了 ${s.tries} 次。` };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_minigame 工具已注册');
}
