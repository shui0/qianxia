/**
 * qqbot_sticker_fight 工具（二次加工新增）
 *
 * 一次性连发 1~5 张表情包。模型只在"该斗图"的时候调它，
 * 调完这一轮就结束，不会进入持续监听状态。
 */
import { runFight } from './sticker-fight.js';

export const FIGHT_TOOL_NAME = 'qqbot_sticker_fight';

export function registerFightTool(ctx, mediaSender, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_sticker_fight 工具未注册');
        return;
    }
    const definition = {
        name: FIGHT_TOOL_NAME,
        description: 'Start a sticker fight: send a burst of 1-5 stickers (not just one) to the current QQ conversation, '
            + 'with a short pause between each. '
            + 'Use when someone says 斗图 / 来图 / 再来一张 / 你行不行, or when the group is trading memes. '
            + 'Don\'t call it in normal conversation — one sticker is enough there (use qqbot_send_sticker).',
        parameters: {
            type: 'object',
            properties: {
                count: {
                    type: 'integer',
                    description: 'How many stickers to send, 1-5. Defaults to 3.',
                },
                query: {
                    type: 'string',
                    description: 'Optional keyword/mood to pick stickers by. Empty = random from preferred folders.',
                },
            },
            required: [],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: {
                    ok: { type: 'boolean' },
                    sent: { type: 'integer' },
                    total: { type: 'integer' },
                },
                required: ['ok', 'sent'],
                additionalProperties: false,
            },
            render: (_a, v) => [{ type: 'text', text: v.ok ? `斗图：连发 ${v.sent} 张` : '库是空的，发不出来' }],
        },
        async execute(args, exec) {
            if (config?.sticker?.enabled !== true) {
                throw new Error('qqbot_sticker_fight: 表情包功能未启用（config.sticker.enabled = false）');
            }
            const replyTarget = exec.agent !== undefined
                ? manager.findByAgent(exec.agent)?.replyTarget
                : undefined;
            if (replyTarget === undefined) {
                throw new Error('qqbot_sticker_fight: 无法确定发送目标');
            }
            const r = await runFight({
                mediaSender, target: replyTarget, config,
                count: args.count, query: args.query, logger,
            });
            if (!r.ok) throw new Error('qqbot_sticker_fight: 表情包库是空的');
            logger.info(`im-qqbot: 斗图连发 ${r.sent} 张 → ${replyTarget.scope}:${replyTarget.targetId}`);
            return { ok: true, sent: r.sent, total: r.total };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_sticker_fight 工具已注册');
}
