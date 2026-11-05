/**
 * qqbot_group_report 工具（二次加工新增）
 *
 * 让千夏自己生成并发送一份群周报。数据源是本地记忆，不发任何外部请求。
 */
import { buildReport } from "./group-report.js";

export const GROUP_REPORT_TOOL_NAME = 'qqbot_group_report';

export function registerGroupReportTool(ctx, sender, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_group_report 工具未注册');
        return;
    }
    const definition = {
        name: GROUP_REPORT_TOOL_NAME,
        description: 'Generate and send a weekly group chat report (message count, most active members, '
            + 'hot topics, notable quotes) built from local memory. '
            + 'Use when someone asks for 周报 / 群报 / 总结一下这周聊了啥. '
            + 'Set send=false to only preview the text without sending.',
        parameters: {
            type: 'object',
            properties: {
                days: {
                    type: 'integer',
                    description: 'How many days to cover. Defaults to 7 (a week).',
                },
                send: {
                    type: 'boolean',
                    description: 'Whether to send it to the chat. Defaults to true.',
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
                    count: { type: 'integer' },
                    days: { type: 'integer' },
                    preview: { type: 'string' },
                },
                required: ['sent', 'count', 'days'],
                additionalProperties: false,
            },
            render: (_args, value) => {
                const v = value;
                return [{ type: 'text', text: v.sent ? `群报已发送（${v.count} 条消息 / ${v.days} 天）` : `群报预览：${v.preview ?? ''}` }];
            },
        },
        async execute(args, exec) {
            const days = Number.isInteger(args.days) && args.days > 0 && args.days <= 90 ? args.days : 7;
            const result = buildReport({ days });
            if (!result.ok) {
                const why = result.reason === 'no-memory'
                    ? '长期记忆没启用'
                    : '这段时间还没有聊天记录';
                throw new Error(`qqbot_group_report: ${why}，攒不出来`);
            }
            if (args.send === false) {
                return { sent: false, count: result.count, days, preview: result.text.slice(0, 500) };
            }
            // 发送目标：当前会话
            const replyTarget = exec.agent !== undefined
                ? manager.findByAgent(exec.agent)?.replyTarget
                : undefined;
            if (replyTarget === undefined) {
                throw new Error('qqbot_group_report: 无法确定发送目标');
            }
            await sender.sendMarkdown(replyTarget, result.text);
            logger.info(`im-qqbot: 群报已发送 (${result.count} 条) → ${replyTarget.scope}:${replyTarget.targetId}`);
            return { sent: true, count: result.count, days };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_group_report 工具已注册');
}
