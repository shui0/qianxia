/**
 * qqbot_diary 工具（二次加工新增）
 *
 * 三个动作：
 *   write —— 她写一条今天的日记（text 必填，但可以不填：不填就返回素材让她自己写）
 *   read  —— 翻最近几条
 *   draft —— 直接拿今天的"素材"（谁在、聊了啥、几句原话），供她自己组织语言
 */
import { writeDiary, readDiary, diaryMaterial } from './diary.js';

export const DIARY_TOOL_NAME = 'qqbot_diary';

export function registerDiaryTool(ctx, manager, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_diary 工具未注册');
        return;
    }
    const definition = {
        name: DIARY_TOOL_NAME,
        description: 'Keep a personal diary about what happened in the group today. '
            + 'action="write" saves a short entry (first person, 60-120 chars); '
            + 'action="read" shows the latest entries; '
            + 'action="draft" returns today\'s raw material (who talked, hot topics, a couple of quotes) '
            + 'so you can compose an entry yourself. '
            + 'Use when someone asks 写日记 / 今天记了什么 / 你昨天日记写了啥.',
        parameters: {
            type: 'object',
            properties: {
                action: {
                    type: 'string',
                    enum: ['write', 'read', 'draft'],
                    description: 'What to do. Defaults to read.',
                },
                text: {
                    type: 'string',
                    description: 'For action=write: the diary entry, first person, under 400 chars.',
                },
                limit: {
                    type: 'integer',
                    description: 'For action=read: how many entries. Defaults to 3.',
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
                    action: { type: 'string' },
                    date: { type: 'string' },
                    entries: {
                        type: 'array',
                        items: {
                            type: 'object',
                            properties: {
                                date: { type: 'string' },
                                text: { type: 'string' },
                            },
                            required: ['date', 'text'],
                        },
                    },
                    material: { type: 'string' },
                },
                required: ['ok', 'action'],
                additionalProperties: false,
            },
            render: (_args, v) => {
                if (v.action === 'write') return [{ type: 'text', text: v.ok ? `日记写好了（${v.date}）` : '日记没写成' }];
                if (v.action === 'read') return [{ type: 'text', text: (v.entries ?? []).map((e) => `${e.date}：${e.text}`).join('\n') || '还没写过日记' }];
                return [{ type: 'text', text: v.material ?? '今天没什么素材' }];
            },
        },
        execute(args, exec) {
            const action = typeof args.action === 'string' ? args.action : 'read';
            // 群 id：优先当前会话的 targetId
            const peerId = manager.findByAgent(exec.agent)?.replyTarget?.targetId;
            if (!peerId) throw new Error('qqbot_diary: 找不到当前群，写不了日记');
            if (action === 'write') {
                const r = writeDiary(peerId, args.text);
                return { ok: r.ok, action, date: r.date };
            }
            if (action === 'read') {
                const n = Number.isInteger(args.limit) && args.limit > 0 && args.limit <= 20 ? args.limit : 3;
                return {
                    ok: true,
                    action,
                    entries: readDiary(peerId, n).map((e) => ({ date: e.date, text: e.text })),
                };
            }
            // draft
            const m = diaryMaterial(peerId);
            if (!m || m.empty) return { ok: true, action, material: '今天群里还没人说话，没什么好写的' };
            const lines = [];
            lines.push(`今天 ${m.count} 条消息，${m.people.length} 个人在说话：`);
            lines.push(m.people.map(([n, c]) => `${n} ${c} 条`).join('、'));
            if (m.topics?.length) lines.push(`聊到的：${m.topics.join('、')}`);
            for (const q of m.quotes ?? []) lines.push(`原话：「${q.t}」—— ${q.n}`);
            return { ok: true, action, material: lines.join('\n') };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_diary 工具已注册');
}
