/**
 * qqbot_affinity 工具（二次加工新增）
 *
 * 查某个人在千夏这儿的好感度。数据在 users/<openid>.json 里，
 * 由每条消息悄悄累加（见 memoryRecorder）。
 */
import { affinityLevel, getMemoryStore } from "./memory-store.js";

export const AFFINITY_TOOL_NAME = 'qqbot_affinity';

function card(profile) {
    const v = Number(profile.affinity) || 0;
    return {
        name: profile.name || '这位',
        value: Math.round(v),
        level: affinityLevel(v),
        messages: profile.messages ?? 0,
    };
}

export function registerAffinityTool(ctx, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_affinity 工具未注册');
        return;
    }
    const definition = {
        name: AFFINITY_TOOL_NAME,
        description: 'Check how much 千夏 likes someone (a 0-999 affinity score with a level label). '
            + 'Pass a nickname to look one person up, or leave it empty to see the top people. '
            + 'Use when someone asks 好感度 / 你喜欢我吗 / 你最喜欢谁.',
        parameters: {
            type: 'object',
            properties: {
                name: {
                    type: 'string',
                    description: 'Nickname to look up. Omit to list the people with the highest affinity.',
                },
                top: {
                    type: 'integer',
                    description: 'When name is omitted, how many people to list. Defaults to 5.',
                },
            },
            required: [],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: {
                    found: { type: 'boolean' },
                    name: { type: 'string' },
                    value: { type: 'integer' },
                    level: { type: 'string' },
                    messages: { type: 'integer' },
                    top: {
                        type: 'array',
                        items: {
                            type: 'object',
                            properties: {
                                name: { type: 'string' },
                                value: { type: 'integer' },
                                level: { type: 'string' },
                            },
                            required: ['name', 'value', 'level'],
                        },
                    },
                },
                required: ['found'],
                additionalProperties: false,
            },
            render: (_args, v) => {
                if (!v.found) return [{ type: 'text', text: '还没有这个人的档案' }];
                if (v.top) return [{ type: 'text', text: v.top.map((x) => `${x.name} ${x.value}(${x.level})`).join('、') }];
                return [{ type: 'text', text: `${v.name}：好感 ${v.value}（${v.level}），聊过 ${v.messages} 次` }];
            },
        },
        execute(args) {
            const mem = getMemoryStore();
            if (!mem) throw new Error('qqbot_affinity: 长期记忆没启用，没有档案可查');
            const name = typeof args.name === 'string' ? args.name.trim() : '';
            if (name) {
                const p = mem.findUserByName(name);
                if (!p) return { found: false };
                return { found: true, ...card(p) };
            }
            const n = Number.isInteger(args.top) && args.top > 0 && args.top <= 20 ? args.top : 5;
            const all = mem.listUsers()
                .map((id) => mem.readProfile(id))
                .filter(Boolean)
                .sort((a, b) => (b.affinity ?? 0) - (a.affinity ?? 0))
                .slice(0, n)
                .map((p) => {
                    const c = card(p);
                    return { name: c.name, value: c.value, level: c.level };
                });
            return { found: all.length > 0, top: all };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_affinity 工具已注册');
}
