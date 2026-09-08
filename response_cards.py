"""Shared Components V2 delivery for channels and interaction follow-ups."""
from time import time

import discord

from component_templates import build_layout_view, template_placeholders

GOLD = 0xD4AF37
ERROR = 0xE74C3C
GREEN = 0x2ECC71
ORANGE = 0xE67E22
BODY_LIMIT = 3000


def build_response_views(title, body, *, footer=None, error=False, accent=None, files=(), thumbnail=None):
    body = body or 'Done.'
    if error:
        accent = ERROR
    elif accent is None:
        accent = GOLD
    # Preserve the entire response. Each page leaves room for title and footer
    # below Discord's 4,000 aggregate display-character budget.
    chunks = [body[i:i + BODY_LIMIT] for i in range(0, len(body), BODY_LIMIT)]
    views = []
    for index, chunk in enumerate(chunks):
        page = f' · {index + 1}/{len(chunks)}' if len(chunks) > 1 else ''
        view = build_layout_view('wiki_response_card' if thumbnail else 'response_card', {
            'thumbnail': thumbnail,
            'title': str(title)[:180] + page,
            'body': chunk if chunk.strip() else '\u200b' + chunk,
            'footer': str(footer or f'Babylon Helper · <t:{int(time())}:t>')[:350],
            'accent_color': accent,
        })
        if index == 0:
            for file in files:
                uri = f'attachment://{file.filename}'
                if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    view.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(
                        uri, description=file.filename,
                    )))
                else:
                    view.add_item(discord.ui.File(uri))
        views.append(view)
    return views


async def send_card(send, title, body, *, footer=None, error=False, accent=None, files=(), ephemeral=None, thumbnail=None):
    """Send only V2 components and explicitly referenced attachments, never embeds/content."""
    files = list(files)
    try:
        views = build_response_views(title, body, footer=footer, error=error, accent=accent, files=files, thumbnail=thumbnail)
        for index, view in enumerate(views):
            kwargs = {'view': view, 'allowed_mentions': discord.AllowedMentions.none()}
            if index == 0 and files:
                kwargs['files'] = files
            if ephemeral is not None:
                kwargs['ephemeral'] = ephemeral
            await send(**kwargs)
    finally:
        for file in files:
            file.close()


def _production_text(body: str) -> str:
    """Make an AI answer safe inside the template's plain-text code block."""
    import re
    text = str(body or "")
    text = re.sub(r"```(?:markdown|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("&nbsp;", " ").replace("\r", "")
    text = re.sub(r"\[source-[^\]]+\]", "", text, flags=re.IGNORECASE)
    # The local vault has no factory-parcel construction page. Do not let a
    # model-generated claim survive into a structured factory card.
    unsupported_factory = bool(re.search(r"factory\s+parcel|parcel type|only parcel that can (?:hold|house|contain) production", text, re.IGNORECASE))
    text = re.sub(r"[^\n]*(?:factory\s+parcel|parcel type|only parcel that can (?:hold|house|contain) production)[^\n]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    lines = []
    if unsupported_factory:
        lines.append("Some machine types require indoor spaces.")
    for line in text.splitlines():
        line = line.strip()
        if not line or set(line) <= set("|-: "):
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]
            line = " · ".join(cells)
        line = re.sub(r"^[-*+]\s+", "• ", line)
        line = re.sub(r"^#+\s*", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)[:900] or "No additional verified calculation details were returned."


def _compact_layout_sketch(machine: str, output: str, limit: int = 44) -> str:
    sketch = f"{machine} -> {output}"
    if len(sketch) <= limit:
        return sketch
    machine_short = machine.split()[-1] if machine else "Machine"
    output_short = output.split()[-1] if output else "Output"
    sketch = f"{machine_short} -> {output_short}"
    if len(sketch) <= limit:
        return sketch
    return sketch[:limit]


def build_production_view(item_name, body, *, wiki_context="", item_wiki_url="https://wiki.capitalrift.com/", item_image_url="https://wiki.capitalrift.com/icons/box.png", footer=None, accent=GOLD):
    """Render the reviewed production-line template from verified wiki data."""
    values = {key: "Not stated in the retrieved wiki" for key in template_placeholders("production_line")}
    values.update({
        "item_name": str(item_name)[:120], "item_wiki_url": item_wiki_url,
        "item_image_url": item_image_url, "target_rate": "See verified request",
        "machine_name": "See verified recipe", "recipe_name": "Verified recipe details",
        "output_per_cycle": "See source", "cycle_time": "See source",
        "recipe_inputs": "See source", "input_cost": "See source",
        "machine_count": "See calculation", "input_rates": "See verified recipe note",
        "layout_sketch": "[machine] -> [output]",
        "storage_plan": "Use storage appropriate to the verified output and inputs.",
        "data_quality": "-# Values shown only when supported by the Capital Rift wiki.",
    })
    verified = ""
    if wiki_context:
        try:
            import json
            import re
            from wiki_cards import format_wiki_note
            payload = json.loads(wiki_context)
            target_override = payload.get("target_rate")
            note = payload.get("exact_note") or payload.get("data")
            if isinstance(note, dict) and note.get("content"):
                content = note["content"]
                verified = format_wiki_note(note).get("body", "")
                front = re.match(r"\A---\s*\n(.*?)\n---", content.lstrip("\ufeff"), re.S)
                metadata = {}
                if front:
                    for line in front[1].splitlines():
                        match = re.match(r"^([a-z_]+):\s*(.+)$", line)
                        if match:
                            metadata[match[1]] = match[2].strip().strip("\"'")
                machine = metadata.get("recipe_machine", "").replace("[[", "").replace("]]", "")
                ingredients = re.findall(r"^\|\s*([^|]+)\s*\|\s*\[\[([^#|]+)", content, re.M)
                ingredient_text = ", ".join(f"{qty.strip()} × {name.strip().rstrip("]").strip()}" for qty, name in ingredients[:8])
                values.update({
                    "target_rate": f"{metadata.get('recipe_rate_per_minute', 'Not stated')}/min",
                    "machine_name": machine or "Not stated in the retrieved wiki",
                    "recipe_name": metadata.get("recipe_name", "Verified recipe"),
                    "output_per_cycle": f"{metadata.get('recipe_output_quantity', 'Not stated')} × {metadata.get('name', item_name)}",
                    "cycle_time": f"{metadata.get('recipe_rate_per_minute', 'Not stated')}/min published rate",
                    "recipe_inputs": ingredient_text or "Not stated in the retrieved wiki",
                    "input_cost": f"${metadata.get('recipe_input_cost', 'Not stated')}",
                    "machine_count": "1", "input_rates": ingredient_text or "See verified recipe note",
                    "production_math": f"1 {machine or 'machine'} produces {metadata.get('recipe_output_quantity', 'the stated output')} {metadata.get('name', item_name)} at {metadata.get('recipe_rate_per_minute', 'the published')} per minute.",
                    # Placement describes where the item can be placed, not a
                    # production-line storage buffer. Keep it out of this
                    # section unless the wiki explicitly provides storage
                    # guidance.
                    "layout_sketch": _compact_layout_sketch(machine or "Machine", metadata.get("name", item_name)),
                    "storage_plan": "Storage details are not stated in the retrieved wiki.",
                    "item_wiki_url": metadata.get("source", item_wiki_url),
                    "item_image_url": metadata.get("image", item_image_url),
                })
                try:
                    desired = float(target_override)
                    published = float(metadata.get("recipe_rate_per_minute", 0))
                    if desired > 0 and published > 0:
                        import math
                        machines = max(1, math.ceil(desired / published))
                        output_name = metadata.get("name", item_name)
                        values.update({
                            "target_rate": f"{desired:g}/min",
                            "machine_count": str(machines),
                            "production_math": f"{machines} {machine or 'machines'} produce {desired:g} {output_name}/min at the published wiki rate.",
                            "layout_sketch": _compact_layout_sketch(f"{machines}x {machine or 'Machine'}", output_name),
                        })
                except (TypeError, ValueError):
                    pass
        except (TypeError, ValueError, json.JSONDecodeError):
            verified = ""
    if "production_math" not in values or values["production_math"] == "Not stated in the retrieved wiki":
        values["production_math"] = _production_text(verified or body)
    return build_layout_view("production_line", values)


async def send_production_card(send, item_name, body, *, wiki_context="", footer=None, item_wiki_url="https://wiki.capitalrift.com/", item_image_url="https://wiki.capitalrift.com/icons/box.png", ephemeral=None):
    view = build_production_view(item_name, body, wiki_context=wiki_context, footer=footer, item_wiki_url=item_wiki_url, item_image_url=item_image_url)
    kwargs = {"view": view, "allowed_mentions": discord.AllowedMentions.none()}
    if ephemeral is not None:
        kwargs["ephemeral"] = ephemeral
    await send(**kwargs)


def _factory_link(label, source):
    from urllib.parse import quote
    label = discord.utils.escape_markdown(str(label)[:120]).replace("\n", " ")
    if source and len(source) <= 1000:
        return f"[{label}]({quote(source, safe=':/?#&=%')})"
    return label + " (source link missing)"


def build_factory_views(plan):
    """Paginate complete stages without cutting a wiki link or hiding a branch."""
    def rate(value):
        return f"{float(value):.6g}"

    blocks = [
        f"**Target:** {_factory_link(plan.target.name, plan.target.source)} · {rate(plan.rate)}/min\n"
        + ("**Partial plan — missing wiki data below.**\n" if not plan.complete else "")
        + "Input rates match the target; rounded machines have spare capacity. "
          "Machine counts cover production, excluding machine construction materials."
    ]
    heading = "Known machine totals (partial)" if not plan.complete else "Machine totals"
    blocks.append(f"**{heading} · {sum(plan.machine_totals.values()):,}**")
    for machine, count in sorted(plan.machine_totals.items()):
        blocks.append(f"• {count:,} × {_factory_link(machine, plan.machine_sources.get(machine))}")
    blocks.append("**Raw-material / external inputs · per minute**")
    if not plan.inputs:
        blocks.append("No resolved raw inputs. Check missing wiki data below.")
    for stage in sorted(plan.inputs, key=lambda s: s.recipe.name):
        label = "" if stage.recipe.raw else " · acquisition unverified"
        blocks.append(f"• {_factory_link(stage.recipe.name, stage.recipe.source)} · {rate(stage.required)}/min{label}")
    blocks.append("**Production stages · upstream → final**")
    for index, stage in enumerate(plan.stages, 1):
        recipe = stage.recipe
        count = f"{stage.machines:,}" if stage.machines is not None else "unknown count"
        published = f"{rate(recipe.rate)}/min each" if recipe.rate else "rate missing"
        machine = discord.utils.escape_markdown(recipe.machine or "machine missing")
        blocks.append(
            f"**{index}.** {_factory_link(recipe.name, recipe.source)} · **{rate(stage.required)}/min**\n"
            f"{count} × {machine} · {published}"
        )
    if plan.placements:
        blocks.append("**Machine placement · stated in wiki**")
        for machine, placement in plan.placements:
            blocks.append(f"• {_factory_link(machine, plan.machine_sources.get(machine))}: {discord.utils.escape_markdown(placement)}")
    if plan.issues:
        blocks.append("**Missing wiki data**")
        blocks.extend("• " + discord.utils.escape_markdown(issue) for issue in dict.fromkeys(plan.issues))
    pages, current = [], []
    for block in blocks:
        # Individual records stay intact; imported note names/URLs are bounded.
        if len(block) > BODY_LIMIT:
            raise ValueError("A wiki record is too long for a production card.")
        if current and (sum(map(len, current)) + len(current) * 2 + len(block) > 2700 or len(current) >= 10):
            pages.append("\n\n".join(current))
            current = []
        current.append(block)
    if current:
        pages.append("\n\n".join(current))
    return [
        build_layout_view("response_card", {
            "title": f"Full factory · {plan.target.name[:100]} · {index + 1}/{len(pages)}",
            "body": body,
            "footer": "Capital Rift local wiki · Published recipe rates · Demand combined before rounding",
            "accent_color": ORANGE if not plan.complete else GOLD,
        })
        for index, body in enumerate(pages)
    ]


async def send_factory_plan(send, plan, *, ephemeral=None):
    for view in build_factory_views(plan):
        kwargs = {"view": view, "allowed_mentions": discord.AllowedMentions.none()}
        if ephemeral is not None:
            kwargs["ephemeral"] = ephemeral
        await send(**kwargs)
