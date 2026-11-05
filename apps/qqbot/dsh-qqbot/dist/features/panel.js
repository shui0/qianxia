/**
 * 指令面板（QQ 官方原生菜单）—— 二次加工新增
 *
 * 这是 QQ 开放平台的「指令面板」能力，不是我们自己发的文本菜单：
 * 用户在群里 @机器人 时，客户端会展示一个原生面板，点某个指令就把文字填进输入框。
 * 相关接口：
 *   POST /v2/panels            创建面板（最多 20 个）
 *   PUT  /v2/panels/{panel_id} 修改面板
 * 面板元素 name ≤ 14 字符、desc ≤ 30 字符、一个面板最多 20 个元素。
 *
 * 本模块只负责"把我们支持的功能翻译成面板元素，并在启动时同步一次"。
 * 同步是幂等的：panel_id 存在就 PUT 更新，不存在就 POST 创建并存下来，
 * 避免每次重启都堆一个新面板（最多 20 个，堆几次就满了）。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { getMemoryStore } from './memory-store.js';

/** 面板里的指令（点一下 = 把 name 填进输入框） */
export const COMMANDS = [
    { type: 'command', name: '菜单', desc: '看看千夏会什么' },
    { type: 'command', name: '周报', desc: '这周群里聊了啥' },
    { type: 'command', name: '日记', desc: '千夏写的日记' },
    { type: 'command', name: '好感度', desc: '千夏有多喜欢你' },
    { type: 'command', name: '掷骰子', desc: '随手掷个骰子' },
    { type: 'command', name: '猜数字', desc: '来一局猜数字' },
    { type: 'command', name: '抽一个', desc: '从群里抽个人' },
    { type: 'command', name: '表情包', desc: '发一张表情包' },
    { type: 'command', name: '斗图', desc: '连发几张来斗图' },
];

/** 按官方限制裁剪：name ≤14、desc ≤30、最多 20 条 */
export function buildPanel(items = COMMANDS, remark = '千夏的指令面板') {
    const trimmed = items.slice(0, 20).map((it) => ({
        type: it.type === 'link' ? 'link' : 'command',
        name: String(it.name ?? '').slice(0, 14),
        ...(it.desc ? { desc: String(it.desc).slice(0, 30) } : {}),
        ...(it.link ? { link: it.link } : {}),
    })).filter((it) => it.name.length > 0);
    return { scope: 'group', target_type: 'all', panel: { items: trimmed, remark: String(remark).slice(0, 255) } };
}

function statePath() {
    const mem = getMemoryStore();
    const root = mem?.root ?? resolve(process.cwd(), 'qq-memory');
    try { mkdirSync(root, { recursive: true }); } catch { /* ignore */ }
    return join(root, 'panel.json');
}

function readState() {
    const p = statePath();
    if (!existsSync(p)) return {};
    try { return JSON.parse(readFileSync(p, 'utf8')) ?? {}; } catch { return {}; }
}

function writeState(s) {
    try { writeFileSync(statePath(), JSON.stringify(s, null, 2), 'utf8'); } catch { /* ignore */ }
}

/**
 * 同步面板到 QQ。返回 { ok, action, panelId? , error? }
 * 依赖 bot.api（SDK 暴露的裸 API 网关），没有就跳过。
 */
export async function syncPanel(bot, config, logger) {
    if (config?.panel?.enabled !== true) return { ok: false, error: 'disabled' };
    const api = bot?.api;
    if (!api?.post || !api?.put) return { ok: false, error: 'no-api' };
    const payload = buildPanel(config?.panel?.items ?? COMMANDS, config?.panel?.remark);
    const state = readState();
    const existing = state.groupPanelId;
    try {
        if (existing) {
            await api.put(`/v2/panels/${existing}`, payload);
            logger?.info?.(`im-qqbot[panel]: 已更新指令面板 ${existing}（${payload.panel.items.length} 条指令）`);
            return { ok: true, action: 'updated', panelId: existing };
        }
        const res = await api.post('/v2/panels', payload);
        const panelId = res?.panel_id ?? res?.data?.panel_id;
        if (panelId) {
            writeState({ ...state, groupPanelId: panelId });
            logger?.info?.(`im-qqbot[panel]: 已创建指令面板 ${panelId}（${payload.panel.items.length} 条指令）`);
        }
        return { ok: Boolean(panelId), action: 'created', panelId };
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger?.warn?.(`im-qqbot[panel]: 同步失败 ${msg}`);
        return { ok: false, error: msg };
    }
}
