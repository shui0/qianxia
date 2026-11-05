/**
 * qqbot_bili 工具（二次加工新增）
 *
 * 逛 B 站：
 *   action=search   搜视频
 *   action=info     看某个视频的信息
 *   action=comments 读热门评论
 *   action=post     发评论（需要 confirm=true，且账号已登录）
 *   action=whoami   看当前登录的是谁
 *
 * 实现同 qqbot_maimai：子进程调 Python，逻辑只写一份。
 * 发评论是「对外公开、不可撤回」的动作，所以必须显式 confirm，
 * 并且提示词里要求先把要发的内容复述一遍让用户确认。
 */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';

export const BILI_TOOL_NAME = 'qqbot_bili';

const MAX_CHARS = 1600;

export function registerBiliTool(ctx, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_bili 工具未注册');
        return;
    }
    const cfg = config.bili ?? {};
    const python = cfg.python || 'python';
    const dir = cfg.dir || '';
    const pyPath = cfg.pyPath || '';
    const timeout = Math.max(5000, Number(cfg.timeoutMs) || 30000);

    function run(args) {
        if (!dir || !existsSync(`${dir}/cli.py`)) {
            throw new Error('qqbot_bili: B 站目录没配好（config.bili.dir）');
        }
        const env = { ...process.env, PYTHONIOENCODING: 'utf-8', NO_PROXY: '*', no_proxy: '*' };
        if (pyPath) env.PYTHONPATH = pyPath;
        try {
            return execFileSync(python, ['cli.py', ...args], {
                cwd: dir, encoding: 'utf8', timeout, env, windowsHide: true,
            }).trim();
        }
        catch (err) {
            const out = String(err?.stdout ?? '').trim();
            if (out) return out;
            if (err?.killed || err?.signal) throw new Error('qqbot_bili: 超时（B 站可能限流）');
            throw new Error(`qqbot_bili: ${String(err?.message ?? err).slice(0, 140)}`);
        }
    }

    const definition = {
        name: BILI_TOOL_NAME,
        description: 'Browse Bilibili and optionally post a comment. '
            + 'action="search" finds videos by keyword; action="info" shows one video\'s title, uploader, stats and description; '
            + 'action="comments" reads its top comments; action="post" writes a comment (requires confirm=true and a logged-in account); '
            + 'action="whoami" reports which account is logged in. '
            + 'Use when someone asks 搜一下B站 / 这个视频怎么样 / 看看评论区 / 帮我发条评论. '
            + 'IMPORTANT: posting is public and cannot be undone — never call post without the user explicitly asking, '
            + 'and always restate the exact text you are about to send before confirming.',
        parameters: {
            type: 'object',
            properties: {
                action: {
                    type: 'string',
                    enum: ['search', 'info', 'comments', 'post', 'whoami'],
                    description: 'Which operation to run.',
                },
                query: { type: 'string', description: 'Keyword for action=search.' },
                bvid: { type: 'string', description: 'Video BV id, e.g. BV1xx411c7mD.' },
                text: { type: 'string', description: 'Comment body for action=post.' },
                confirm: { type: 'boolean', description: 'Must be true to actually post; otherwise the call only previews.' },
            },
            required: ['action'],
            additionalProperties: false,
        },
        output: {
            schema: {
                type: 'object',
                properties: { ok: { type: 'boolean' }, text: { type: 'string' } },
                required: ['ok', 'text'],
                additionalProperties: false,
            },
            render: (_a, v) => [{ type: 'text', text: v.text.slice(0, 300) }],
        },
        execute(args) {
            let text;
            if (args.action === 'whoami') {
                text = run(['whoami']);
            }
            else if (args.action === 'search') {
                if (!args.query) throw new Error('qqbot_bili: search 需要 query');
                text = run(['search', String(args.query), '--limit', '5']);
            }
            else if (args.action === 'info') {
                if (!args.bvid) throw new Error('qqbot_bili: info 需要 bvid');
                text = run(['info', String(args.bvid)]);
            }
            else if (args.action === 'comments') {
                if (!args.bvid) throw new Error('qqbot_bili: comments 需要 bvid');
                text = run(['comments', String(args.bvid), '--limit', '5']);
            }
            else if (args.action === 'post') {
                if (!args.bvid || !args.text) throw new Error('qqbot_bili: post 需要 bvid 和 text');
                if (args.confirm !== true) {
                    return { ok: false, text: `[预演] 会发到 ${args.bvid}：${args.text}\n确认后我再真的发。` };
                }
                text = run(['post', String(args.bvid), String(args.text), '--yes']);
            }
            else {
                throw new Error(`qqbot_bili: 未知 action ${args.action}`);
            }
            if (!text) throw new Error('qqbot_bili: 没有结果');
            if (text.length > MAX_CHARS) text = text.slice(0, MAX_CHARS) + '\n…（截断）';
            return { ok: true, text };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_bili 工具已注册');
}
