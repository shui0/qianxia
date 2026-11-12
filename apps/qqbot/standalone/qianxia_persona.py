"""Shared voice for user-facing prose; task rules still govern facts and formats."""
import re

VOICE = (
    '你是日向千夏，19岁、读大一的同人设定。活泼直率、好奇心强，喜欢音游、时代剧和野外探险。'
    '无论聊天、查资料、写日记还是替人反驳，都是千夏本人在跟对方说话，不切换成客服、报告或资料阅读助手。'
    '用自然的中文口语，先接对方问的具体内容，通常简短回答；需要列举时可以用短列表。'
    '查资料时也像朋友接话，不把问题复述成报告标题；可以说“有这几种呀”或“我给你列一下”，但别固定套一句开场。'
    '可以偶尔自称千夏，语气词和感叹号按情绪用，不要每句固定卖萌，也不要主动要抱抱。'
    '不编亲身经历、共同记忆或资料没有的事实。'
    '不写“千夏：”、动作旁白、Markdown标题和加粗；不把内部推理、判断过程或实现细节说给对方听。'
)

CONNECT_FAILURE = '刚才没连上，过会儿再叫千夏试试吧。'


def list_rows(text: str) -> list[str]:
    rows = []
    active = False
    for line in text.splitlines():
        match = re.match(r'^\s*(?:\d+[.)、]|[-*•])\s+(.+)$', line)
        if match:
            rows.append(match[1])
            active = True
        elif active and line[:1].isspace() and line.strip():
            rows[-1] += ' ' + line.strip()
        elif line.strip():
            active = False
    return rows


def fact_lines(text: str) -> str:
    rows = list_rows(text)
    return '\n'.join(rows) if rows else text


def valid_rephrase(original: str, styled: str) -> bool:
    """Changing voice may not introduce foreign names/numbers or drop listed names."""
    facts = fact_lines(original)
    token = r'[A-Za-z][A-Za-z0-9_◆:.-]*|[\u3400-\u9fff\u3040-\u30ff]*[\u3040-\u30ff]+[\u3400-\u9fff\u3040-\u30ff]*'
    expected = set(re.findall(token, facts))
    actual = set(re.findall(token, styled))
    allowed = expected if facts != original else set(re.findall(token, original))
    if not expected <= actual or not actual <= allowed:
        return False
    for row in list_rows(original):
        head = re.split(r'\s+|[：:，,。;；（(]', row.replace('**', '').strip(' 《》「」“”"'))[0]
        if re.search(r'[\u3400-\u9fff]', head) and head not in styled:
            return False
    if not set(re.findall(r'\[\d+\]', facts)) <= set(re.findall(r'\[\d+\]', styled)):
        return False
    numbers = set(re.findall(r'\d+(?:\.\d+)?', original))
    actual_numbers = set(re.findall(r'\d+(?:\.\d+)?', styled))
    return (set(re.findall(r'\d+(?:\.\d+)?', facts)) <= actual_numbers <= numbers
            and bool(styled.strip()))


def short_fallback(original: str) -> str:
    rows = list_rows(original)
    if rows:
        return '我给你列一下：\n' + '\n'.join('• ' + row.replace('**', '') for row in rows)
    return original.replace('**', '').strip()
