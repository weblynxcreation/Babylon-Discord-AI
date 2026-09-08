"""Convert imported wiki Markdown into Discord-readable facts without AI."""
import json
import re
from urllib.parse import urlsplit


def https_url(value):
    try:
        parsed = urlsplit(value or '')
        return value if parsed.scheme == 'https' and parsed.hostname else None
    except ValueError:
        return None


def wiki_text(text, links=None):
    links = links or {}
    def replace(match):
        target, _, alias = match[1].partition("|")
        target = target.split("#")[0]
        label = alias or target
        url = https_url(links.get(target))
        return f"[{label}]({url})" if url else label
    return re.sub(r'\[\[([^\]]+)\]\]', replace, text)


def split_wiki_metadata(content):
    """Read the importer's scalar metadata without executing YAML tags."""
    text = (content or '').lstrip('\ufeff')
    metadata = {}
    front = re.match(r'\A---\s*\n(.*?)\n---\s*(?:\n|$)', text, re.S)
    if front:
        # The importer uses simple top-level scalars. Do not execute YAML tags
        # or infer ingredient quantities from its name-only metadata list.
        for line in front[1].splitlines():
            match = re.match(r'^([a-z_]+):\s*(.+)$', line)
            if match:
                value = match[2].strip()
                try:
                    value = json.loads(value)
                except ValueError:
                    value = value.strip("'\"")
                if isinstance(value, (str, int, float)):
                    metadata[match[1]] = str(value)
        text = text[front.end():]
    return metadata, text


def format_wiki_note(note, links=None):
    metadata, text = split_wiki_metadata(note.get('content'))
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'^# [^\n]*\n', '', text, count=1, flags=re.M)
    text = re.split(r'^## (?:Source|Personal notes)\s*$', text, maxsplit=1, flags=re.M)[0]
    text = wiki_text(text, links)
    lines = text.splitlines()
    rendered = []
    has_economics = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|\-]+\|\s*$', lines[i + 1]):
            headers = [v.strip() for v in line.strip().strip('|').split('|')]
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [v.strip() for v in lines[i].strip().strip('|').split('|')]
                if 'Quantity' in headers and 'Item' in headers and len(cells) == len(headers):
                    row = dict(zip(headers, cells))
                    rendered.append(f"- **{row['Quantity']} × {row['Item']}**")
                elif 'Machine' in headers and len(cells) == len(headers):
                    row = dict(zip(headers, cells))
                    stats = [f"**Machine:** {row['Machine']}"]
                    if row.get('Output'):
                        stats.append(f"{row['Output']} output")
                    if row.get('Rate'):
                        stats.append(row['Rate'])
                    rendered.append(' · '.join(stats))
                    economics = [f"{label} {row[key]}" for key, label in (
                        ('Input cost', 'Cost'), ('Output value', 'Value'), ('Profit/min', 'Profit/min')
                    ) if row.get(key)]
                    if economics:
                        rendered.append(' · '.join(economics) + ' (base)')
                        has_economics = True
                else:
                    rendered.extend(f'- **{key}:** {value}' for key, value in zip(headers, cells) if value)
                i += 1
            continue
        # Bold labels occupy less vertical space than Discord headings.
        if line.strip() == '## Recipe':
            i += 1
            continue
        if has_economics and line.startswith('Inputs about '):
            i += 1
            continue
        rendered.append(re.sub(r'^#{2,}\s+(.+)$', r'**\1**', line))
        i += 1
    body = '\n'.join(rendered).strip()
    # The full list remains available through the source link, without letting
    # a widely used material dominate the lookup card.
    used = re.search(r'^\*\*Used in\*\*\s*\n(.*?)(?=^\*\*[^\n]+\*\*\s*$|\Z)', body, re.M | re.S)
    if used:
        entries = [line for line in used[1].splitlines() if line.strip()]
        if len(entries) > 2:
            replacement = '\n'.join(entries[:2]) + f'\n- +{len(entries) - 2} more in the wiki.\n'
            body = body[:used.start(1)] + replacement + body[used.end(1):]
    details = []
    for key, label in (('category', ''), ('base_price', 'Base'), ('stack_size', 'Stack')):
        if metadata.get(key):
            value = metadata[key]
            if key == 'base_price':
                value = '$' + value.removesuffix('.0')
            details.append(f'{label} {value}' if label else value)
    if details:
        body = ' · '.join(details) + '\n\n' + body
    body = re.sub(r'^\*\*Source\*\*\s*\n\[https?://[^]]+\]\(https?://[^)]+\)\s*', '', body, flags=re.M)
    body = re.sub(r'\n{3,}', '\n\n', body)
    source = https_url(metadata.get('source'))
    footer = f'Source: [Capital Rift Wiki]({source})' if source else f"Capital Rift wiki · {note.get('path', 'Source unavailable')}"
    if metadata.get('collected'):
        footer += f" · Collected {metadata['collected']}"
    return {
        'body': body or 'This wiki note has no readable content.',
        'footer': footer,
        'thumbnail': https_url(metadata.get('image')),
    }


async def linked_wiki_card(note):
    """Resolve exact Obsidian note references to their declared public source URLs."""
    from pathlib import PurePosixPath
    from tools.capital_rift import capital_rift_wiki

    links = {}
    targets = dict.fromkeys(
        value.split("|")[0].split("#")[0]
        for value in re.findall(r"\[\[([^\]]+)\]\]", note.get("content", ""))
    )
    for target in list(targets)[:40]:
        relative = PurePosixPath(note.get("path", "")).parent / (target.removesuffix(".md") + ".md")
        payload = json.loads(await capital_rift_wiki("read", note_path=str(relative)))
        data = payload.get("data", {})
        if data.get("error"):
            found = json.loads(await capital_rift_wiki("search", query=target, limit=5))
            matches = found.get("data", {}).get("results", [])
            exact = next((item for item in matches if item.get("title", "").casefold() == target.casefold()), None)
            if not exact:
                continue
            data = json.loads(await capital_rift_wiki("read", note_path=exact["path"])).get("data", {})
        front = re.match(r"\A---\s*\n(.*?)\n---", data.get("content", "").lstrip("\ufeff"), re.S)
        source = re.search(r"^source:\s*(.+)$", front[1], re.M) if front else None
        if source:
            url = https_url(source[1].strip().strip("\"'"))
            if url:
                links[target] = url
    return format_wiki_note(note, links)
