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


def wiki_text(text):
    return re.sub(r'\[\[([^\]]+)\]\]', lambda m: m[1].split('|')[-1].split('#')[0], text)


def format_wiki_note(note):
    text = (note.get('content') or '').lstrip('\ufeff')
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
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'^# [^\n]*\n', '', text, count=1, flags=re.M)
    text = re.split(r'^## (?:Source|Personal notes)\s*$', text, maxsplit=1, flags=re.M)[0]
    text = wiki_text(text)
    lines = text.splitlines()
    rendered = []
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
                    cost = f" · {row['Base cost']} base cost" if row.get('Base cost') else ''
                    rendered.append(f"- **{row['Quantity']} × {row['Item']}**{cost}")
                else:
                    rendered.extend(f'- **{key}:** {value}' for key, value in zip(headers, cells) if value)
                i += 1
            continue
        rendered.append(re.sub(r'^#{4,}\s+', '### ', line))
        i += 1
    body = '\n'.join(rendered).strip()
    # The full list remains available through the source link, without letting
    # a widely used material dominate the lookup card.
    used = re.search(r'^## Used in\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
    if used:
        entries = [line for line in used[1].splitlines() if line.strip()]
        if len(entries) > 6:
            replacement = '\n'.join(entries[:6]) + f'\n- Plus {len(entries) - 6} more entries in the wiki.\n'
            body = body[:used.start(1)] + replacement + body[used.end(1):]
    details = []
    for key, label in (('category', 'Category'), ('base_price', 'Base value'), ('stack_size', 'Stack size'), ('sold_from', 'Sold from')):
        if metadata.get(key):
            value = metadata[key]
            if key == 'base_price':
                value = '$' + value.removesuffix('.0')
            details.append(f'**{label}:** {value}')
    if details:
        body = ' · '.join(details) + '\n\n' + body
    body = re.sub(r'\n{3,}', '\n\n', body)
    source = https_url(metadata.get('source'))
    footer = f'[Capital Rift Wiki]({source})' if source else f"Capital Rift wiki · {note.get('path', 'Source unavailable')}"
    if metadata.get('collected'):
        footer += f" · Collected {metadata['collected']}"
    return {
        'body': body or 'This wiki note has no readable content.',
        'footer': footer,
        'thumbnail': https_url(metadata.get('image')),
    }
