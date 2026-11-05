/**
 * qqbot_maimai 工具（二次加工新增）
 *
 * 把 apps/maimai 的命令行能力接进 QQ：
 *   action=search  按曲名/俗称搜曲
 *   action=song    看某首的全部谱面（含拟合定数、平均达成率）
 *   action=rating  按定数 + 达成率算单谱面 rating
 *   action=player  按查分器用户名查 b50
 *
 * 实现方式是「调子进程」而不是把曲库读进 Node：
 *   搜索/评分逻辑只写一份（Python 里），改一处两边同步；
 *   代价是每次多 ~300ms 启动开销，对聊天场景可以接受。
 */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';

export const MAIMAI_TOOL_NAME = 'qqbot_maimai';

const PY_MAX_CHARS = 1800;

export function registerMaimaiTool(ctx, config, logger) {
    const tools = ctx.get('tools');
    if (!tools?.register) {
        logger.warn('im-qqbot: tools 服务不可用，qqbot_maimai 工具未注册');
        return;
    }
    const cfg = config.maimai ?? {};
    const python = cfg.python || 'python';
    const dir = cfg.dir || '';
    const timeout = Math.max(3000, Number(cfg.timeoutMs) || 20000);

    function run(args) {
        if (!dir || !existsSync(`${dir}/cli.py`)) {
            throw new Error('qqbot_maimai: 曲库目录没配好（config.maimai.dir）');
        }
        try {
            return execFileSync(python, ['cli.py', ...args], {
                cwd: dir,
                encoding: 'utf8',
                timeout,
                env: { ...process.env, PYTHONIOENCODING: 'utf-8', NO_PROXY: '*', no_proxy: '*' },
                windowsHide: true,
            }).trim();
        }
        catch (err) {
            const out = String(err?.stdout ?? '').trim();
            if (out) return out;
            if (err?.killed || err?.signal) throw new Error('qqbot_maimai: 查询超时');
            throw new Error(`qqbot_maimai: ${String(err?.message ?? err).slice(0, 120)}`);
        }
    }

    const definition = {
        name: MAIMAI_TOOL_NAME,
        description: 'Query maimai DX song data and ratings from the local chart database '
            + '(built from the community chart API). '
            + 'action="search" finds songs by title or Chinese nickname (命嫌/六兆年/砂星…); '
            + 'action="song" shows all difficulties of one song with official ds, community-fitted ds, '
            + 'average achievement and play count, and separates ST / DX charts; '
            + 'action="rating" computes the single-chart rating from ds + achievement; '
            + 'action="player" looks up someone\'s b50 by their 查分器 username. '
            + 'Use when someone asks 这首多少级 / 定数多少 / 打这个能加多少分 / 帮我查下成绩.',
        parameters: {
            type: 'object',
            properties: {
                action: {
                    type: 'string',
                    enum: ['search', 'song', 'rating', 'player', 'count'],
                    description: 'Which query to run.',
                },
                query: { type: 'string', description: 'Song title or nickname for search/song.' },
                style: {
                    type: 'string',
                    enum: ['st', 'dx', 'all'],
                    description: 'For action=song: only ST charts, only DX charts, or both (default).',
                },
                ds: { type: 'number', description: 'For action=rating: chart constant.' },
                ach: { type: 'number', description: 'For action=rating: achievement percent, e.g. 100.5.' },
                username: { type: 'string', description: 'For action=player: 查分器 username.' },
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
            const action = args.action;
            let text;
            if (action === 'count') {
                text = run(['count']);
            }
            else if (action === 'rating') {
                if (typeof args.ds !== 'number' || typeof args.ach !== 'number') {
                    throw new Error('qqbot_maimai: rating 需要 ds 和 ach 两个数字');
                }
                text = run(['rating', '--ds', String(args.ds), '--ach', String(args.ach)]);
            }
            else if (action === 'player') {
                if (!args.username) throw new Error('qqbot_maimai: player 需要 username');
                text = run(['player', String(args.username), '--top', '5']);
            }
            else {
                if (!args.query) throw new Error(`qqbot_maimai: ${action} 需要 query`);
                if (action === 'song') {
                    const style = ['st', 'dx', 'all'].includes(args.style) ? args.style : 'all';
                    text = run(['song', String(args.query), '--style', style, '--limit', '1']);
                }
                else {
                    text = run(['search', String(args.query), '--limit', '5']);
                }
            }
            if (!text) throw new Error('qqbot_maimai: 没有查到结果');
            if (text.length > PY_MAX_CHARS) text = text.slice(0, PY_MAX_CHARS) + '\n…（太长了，截断）';
            return { ok: true, text };
        },
    };
    tools.register(definition);
    logger.info('im-qqbot: qqbot_maimai 工具已注册');
}
