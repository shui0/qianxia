"""Select verbatim, query-relevant passages without generating new facts."""
import html
import re
import unicodedata


def normal(text: str) -> str:
    return unicodedata.normalize('NFKC', text).casefold()


def passages(query: str, body: str, limit: int = 800) -> str:
    if limit <= 0:
        return ''
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', body, flags=re.I | re.S)
    body = html.unescape(re.sub(r'<[^>]+>', '', body))
    lines = [' '.join(line.split()) for line in body.splitlines()]
    lines = [line for line in lines if line and '{{' not in line and '}}' not in line]
    if not lines or normal(' '.join(lines)).strip('.… !') in {'loading', 'loading...', '加载中'}:
        return ''
    q = normal(query)
    numbers = {float(value) for value in re.findall(r'\d+(?:\.\d+)?', q)}
    words = set(re.findall(r'[a-z][a-z0-9_-]{1,}', q)) - {'what', 'which', 'the', 'are', 'is', 'of', 'in'}
    han = set()
    for part in re.findall(r'[\u3040-\u30ff\u3400-\u9fff]+', q):
        han.update(part[i:i + 2] for i in range(len(part) - 1))
    han -= {'哪些', '什么', '有哪些', '的是', '这个', '怎么'}

    def score(text):
        value = normal(text)
        found = {float(number) for number in re.findall(r'\d+(?:\.\d+)?', value)}
        numeric = len(numbers & found)
        return numeric * 8 + sum(word in value for word in words) * 2 + sum(word in value for word in han), numeric

    candidates = []
    heading = ''
    table_header = ''
    for index, line in enumerate(lines):
        if line.startswith('#'):
            heading = line
        if index + 1 < len(lines) and re.match(r'^\|?[ :|-]+\|', lines[index + 1]):
            table_header = line + '\n' + lines[index + 1]
        if not line.startswith('|'):
            table_header = ''
        if re.fullmatch(r'[ :|\-]+', line):
            continue
        # Overlap long paragraphs so matches deep in an article remain reachable.
        for offset in range(0, len(line), 440):
            piece = line[max(0, offset - 60):offset + 500]
            value, numeric = score(piece)
            context = []
            if line.startswith('|') and table_header and line not in table_header:
                value += score(heading + ' ' + table_header)[0]
                context.append(table_header)
            elif len(line) < 80 and not line.startswith(('-', '*', '#')):
                # Neighbours help keep a short data cell attached to its record,
                # but may never crowd the actual matching sentence out.
                previous = lines[max(0, index - 3):index]
                if numeric:
                    previous = [part for part in previous
                                if not re.fullmatch(r'[\d\s.+/%·,\-]+(?:人|条|次)?', part)]
                context.append('\n'.join(previous)[-140:])
            elif heading and heading != line:
                context.append(heading)
            context.append(piece)
            candidates.append((value, numeric, index, '\n'.join(context)))
    if not candidates:
        return ''
    ranked = sorted(candidates, key=lambda row: (-row[0], row[2]))
    minimum = ranked[0][0] / 2 if ranked[0][0] else 0
    # Keep the introductory scope/date when available, without spending the budget on navigation.
    intro = '\n'.join(lines[:2])[:min(160, limit // 4)]
    chosen = []
    remaining = limit - len(intro) - 4
    seen = set()
    for value, numeric, index, block in ranked:
        if value < minimum:
            continue
        if block in seen or block in intro:
            continue
        if len(block) > remaining:
            if chosen:
                continue
            block = block[:max(0, remaining)]
        if not block:
            break
        chosen.append((index, block))
        seen.add(block)
        remaining -= len(block) + 2
        if remaining <= 40:
            break
    return (intro + '\n\n' + '\n\n'.join(block for _, block in sorted(chosen)))[:limit].strip()
