/**
 * dsh-im-qqbot 插件配置 Schema
 */
import Schema from '@deepseek-ai/schemastery';
/** 访问控制子 Schema（独立导出：config 路由的服务端校验复用） */
export const AccessControlSchema = Schema.object({
    c2cMode: Schema.union(['open', 'allowlist', 'disabled']).default('open').description('C2C访问模式'),
    c2cAllow: Schema.array(Schema.string()).default([]).description('C2C白名单'),
    groupMode: Schema.union(['open', 'allowlist', 'disabled']).default('open').description('群聊访问模式'),
    groupAllow: Schema.array(Schema.string()).default([]).description('群聊白名单'),
});
/** 群聊回复策略（二次加工新增） */
export const SmartReplySchema = Schema.object({
    enabled: Schema.boolean().default(false).description('启用群聊回复策略（关闭时保持原行为）'),
    keywords: Schema.array(Schema.string()).default([]).description('命中任意关键词就回复（子串匹配）'),
    probability: Schema.number().default(0.2).description('未 @ 且未命中关键词时，回复概率 0~1'),
    cooldownMs: Schema.number().default(120000).description('同一群两次随机接话的最小间隔(ms)'),
});
/** 表情包库（二次加工新增） */
export const StickerSchema = Schema.object({
    enabled: Schema.boolean().default(false).description('启用 qqbot_send_sticker 表情包工具'),
    dir: Schema.string().default('').description('表情包目录，留空用 <cwd>/stickers'),
    prefer: Schema.array(Schema.string()).default([]).description('优先使用的顶层目录名（随机兜底只从这里挑）'),
});
/** 长期记忆（二次加工新增） */
export const MemorySchema = Schema.object({
    enabled: Schema.boolean().default(true).description('启用长期记忆（消息落盘 + 用户专属档案）'),
    dir: Schema.string().default('').description('记忆目录，留空用 <cwd>/qq-memory'),
    recentLimit: Schema.number().default(20).description('注入多少条最近的群消息（越小越省 token）'),
    lineChars: Schema.number().default(120).description('单条消息注入时的截断字数'),
});
export const ConfigSchema = Schema.object({
    appId: Schema.string().default('').description('QQ 机器人 AppID'),
    appSecret: Schema.string().default('').description('QQ 机器人 AppSecret'),
    provider: Schema.string().description('LLM provider name'),
    model: Schema.string().description('Model name'),
    preset: Schema.string().description('Agent preset id'),
    cwd: Schema.string().description('Agent working directory'),
    requireMention: Schema.boolean().default(true).description('群聊是否需要@bot触发'),
    groupPrompt: Schema.string().description('群聊额外system prompt'),
    directPrompt: Schema.string().description('私聊额外system prompt'),
    textChunkLimit: Schema.number().default(4500).description('单条消息最大字符数'),
    streaming: Schema.boolean().default(true).description('是否启用流式输出（群聊始终不启用）'),
    sessionIdleTimeout: Schema.number().default(30 * 60 * 1000).description('会话闲置超时(ms)'),
    maxQueue: Schema.number().default(20).description('并发队列最大长度'),
    processingTimeoutMs: Schema.number().default(30 * 60 * 1000).description('处理超时(ms)，超时中断当前 LLM 调用'),
    askTimeoutMs: Schema.number().default(5 * 60 * 1000).description('待答问题超时(ms)，超时自动拒绝并提示'),
    historyLimit: Schema.number().default(10).description('群历史缓冲条数'),
    access: AccessControlSchema.default({
        c2cMode: 'open',
        c2cAllow: [],
        groupMode: 'open',
        groupAllow: [],
    }).description('访问控制'),
    showToolResults: Schema.boolean().default(false).description('是否展示工具调用成功结果（错误始终展示）'),
    debug: Schema.boolean().default(false),
    media: Schema.object({
        enabled: Schema.boolean().default(true).description('是否启用富媒体理解（图片/视频下载 + 工具分析）'),
        maxMB: Schema.number().default(200).description('富媒体下载大小上限(MB)'),
        ttlHours: Schema.number().default(24).description('富媒体存活时长(小时)，0=永不过期'),
    }).default({
        enabled: true,
        maxMB: 200,
        ttlHours: 24,
    }).description('富媒体理解配置'),
    vision: Schema.object({
        enabled: Schema.boolean().default(false).description('是否启用视觉理解（qqbot_describe_image 工具）'),
        provider: Schema.string().default('').description('视觉模型 provider（dsh 注册的 llm adapter，如 pi-ai）'),
        model: Schema.string().default('').description('视觉模型 id（如 qwen-vl-max）'),
        defaultPrompt: Schema.string().default('Describe this image in detail.').description('默认描述 prompt'),
        maxBytes: Schema.number().default(10 * 1024 * 1024).description('图片字节上限'),
        maxTokens: Schema.number().default(1024).description('输出 token 上限'),
        timeoutMs: Schema.number().default(120000).description('视觉调用超时(ms)'),
    }).default({
        enabled: false,
        provider: '',
        model: '',
        defaultPrompt: 'Describe this image in detail.',
        maxBytes: 10 * 1024 * 1024,
        maxTokens: 1024,
        timeoutMs: 120000,
    }).description('视觉理解配置'),
    memory: MemorySchema.default({ enabled: true, dir: '', recentLimit: 20, lineChars: 120 }).description('长期记忆'),
    smartReply: SmartReplySchema.default({ enabled: false, keywords: [], probability: 0.2, cooldownMs: 120000 }).description('群聊回复策略'),
    silenceMarker: Schema.string().default('[SILENT]').description('模型输出该标记表示本轮不说话'),
    sticker: StickerSchema.default({ enabled: false, dir: '' }).description('表情包库'),
    replyDelay: Schema.object({
        enabled: Schema.boolean().default(false).description('延迟发送开关'),
        minSec: Schema.number().default(0).description('最小延迟（秒）'),
        maxSec: Schema.number().default(1800).description('最大延迟（秒），上限 1500 生效'),
        onlyProactive: Schema.boolean().default(true).description('只延迟"趁机搭话"的轮次，被 @ 时秒回'),
    }).default({ enabled: false, minSec: 0, maxSec: 1800, onlyProactive: true }).description('回复延迟'),
    proactiveTalk: Schema.object({
        enabled: Schema.boolean().default(false).description('不相关消息时，过一会儿主动 @ 人搭话'),
        probability: Schema.number().default(0.1).description('触发搭话的概率 0~1'),
        minSec: Schema.number().default(30).description('最短延迟（秒）'),
        maxSec: Schema.number().default(240).description('最长延迟（秒）——超过被动回复窗口会失败'),
    }).default({ enabled: false, probability: 0.1, minSec: 30, maxSec: 240 }).description('主动搭话'),
    mention: Schema.object({
        enabled: Schema.boolean().default(false).description('允许 @ 别人（需要 markdown 消息权限）'),
    }).default({ enabled: false }).description('@ 能力'),
    stickerFight: Schema.object({
        count: Schema.number().default(3).description('斗图一次连发几张（上限 5）'),
        gapMs: Schema.number().default(2500).description('每张之间的间隔(ms)'),
    }).default({ count: 3, gapMs: 2500 }).description('斗图模式'),
    panel: Schema.object({
        enabled: Schema.boolean().default(false).description('同步 QQ 原生指令面板（@机器人时展示的菜单）'),
        remark: Schema.string().default('千夏的指令面板').description('面板备注（不对用户展示）'),
    }).default({ enabled: false, remark: '千夏的指令面板' }).description('指令面板'),
    voice: Schema.object({
        enabled: Schema.boolean().default(false).description('启用语音条（qqbot_say）'),
        endpoint: Schema.string().default('').description('推理服务地址，POST JSON {text, speaker}'),
        token: Schema.string().default('').description('Bearer token（没有就留空）'),
        speaker: Schema.string().default('').description('默认音色/模型 id'),
        format: Schema.string().default('wav').description('期望的音频格式 wav/mp3'),
        timeoutMs: Schema.number().default(30000).description('推理超时(ms)'),
    }).default({ enabled: false, endpoint: '', token: '', speaker: '', format: 'wav', timeoutMs: 30000 }).description('语音条'),
    sendFile: Schema.object({
        restrictPaths: Schema.boolean().default(true).description('是否启用路径白名单（默认 true，仅允许 media + cwd + extraRoots）'),
        extraRoots: Schema.array(Schema.string()).default([]).description('额外允许访问的根目录'),
        sendPresentedFiles: Schema.boolean().default(true).description('是否将 present 声明的交付文件发送到当前会话'),
        maxFiles: Schema.number().default(4).description('单轮最多投递的交付文件数'),
    }).default({
        restrictPaths: true,
        extraRoots: [],
        sendPresentedFiles: true,
        maxFiles: 4,
    }).description('附件发送配置'),
});
//# sourceMappingURL=config.js.map