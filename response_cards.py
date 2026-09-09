"""Shared Components V2 delivery for channels and interaction follow-ups."""
from time import time

import discord

from component_templates import build_layout_view, template_placeholders

from card_primitives import GOLD, ERROR, GREEN, ORANGE, BODY_LIMIT, build_card, paginate_text, validate_view
from observability import mark_delivery, mark_status


def build_response_views(title, body, *, footer=None, error=False, accent=None, files=(), thumbnail=None, state="info"):
    if not body:
        body = 'No results found.'
        if not error:
            state = 'empty'
    if error:
        state = 'error'
    elif state == 'info' and accent in (GREEN, ORANGE):
        state = 'success' if accent == GREEN else 'warning'
    if error:
        accent = ERROR
    # Preserve the entire response. Each page leaves room for title and footer
    # below Discord's 4,000 aggregate display-character budget.
    chunks = paginate_text(body)
    views = []
    for index, chunk in enumerate(chunks):
        page = f' · {index + 1}/{len(chunks)}' if len(chunks) > 1 else ''
        view = build_card(
            str(title)[:180] + page, chunk,
            footer=str(footer or f'Babylon Helper · <t:{int(time())}:t>')[:350],
            state=state, accent=accent, thumbnail=thumbnail,
        )
        if index == 0:
            for file in files:
                uri = f'attachment://{file.filename}'
                if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    view.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(
                        uri, description=file.filename,
                    )))
                else:
                    view.add_item(discord.ui.File(uri))
        views.append(validate_view(view))
    return views


async def send_card(send, title, body, *, footer=None, error=False, accent=None, files=(), ephemeral=None, thumbnail=None, state="info"):
    """Send only V2 components and explicitly referenced attachments, never embeds/content."""
    files = list(files)
    if error or state == "error":
        mark_status("error")
    try:
        views = build_response_views(title, body, footer=footer, error=error, accent=accent, files=files, thumbnail=thumbnail, state=state)
        for index, view in enumerate(views):
            kwargs = {'view': view, 'allowed_mentions': discord.AllowedMentions.none()}
            if index == 0 and files:
                kwargs['files'] = files
            if ephemeral is not None:
                kwargs['ephemeral'] = ephemeral
            await send(**kwargs)
            mark_delivery()
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
    mark_delivery()


def _factory_link(label, source):
    from urllib.parse import quote
    label = discord.utils.escape_markdown(str(label)[:120]).replace("\n", " ")
    if source and len(source) <= 1000:
        return f"[{label}]({quote(source, safe=':/?#&=%')})"
    return label + " (source link missing)"



def _factory_pages(plan):
    """Separate the overview from short, independently browsable detail pages."""
    def rate(value):
        return f"{float(value):.6g}"

    partial = "**Partial plan · check Notes for missing data.**\n\n" if not plan.complete else ""
    target = _factory_link(plan.target.name, plan.target.source)
    final = next((s for s in plan.stages if s.recipe.path == plan.target.path), None)
    overview = (
        f"{partial}{target}\n**{rate(plan.rate)} / min** · {rate(plan.rate * 60)} / hour\n\n"
        f"**{sum(plan.machine_totals.values()):,} {'known ' if not plan.complete else ''}machines** · "
        f"{len(plan.machine_totals)} types\n"
        f"**{len(plan.stages)} production stages** · {len(plan.inputs)} raw / external inputs"
    )
    if final:
        count = f"{final.machines:,}" if final.machines is not None else "Unknown"
        overview += (
            "\n\n**Final assembly**\n"
            f"{count} × {_factory_link(final.recipe.machine or 'Machine unknown', plan.machine_sources.get(final.recipe.machine))}"
        )
    overview += "\n\nChoose a section below to see the breakdown."
    pages = [("Overview", overview)]

    def section(name, rows, size=6):
        rows = rows or ["No verified data available."]
        current = []
        for row in rows:
            if len(row) > BODY_LIMIT:
                raise ValueError("A wiki record is too long for a production card.")
            if current and (len(current) >= size or len("\n\n".join(current + [row])) > 2500):
                pages.append((name, "\n\n".join(current)))
                current = []
            current.append(row)
        if current:
            pages.append((name, "\n\n".join(current)))

    section("Inputs", [
        f"**{rate(s.required)} / min** · {_factory_link(s.recipe.name, s.recipe.source)}"
        + ("\n-# Acquisition unverified in the wiki." if not s.recipe.raw else "")
        for s in sorted(plan.inputs, key=lambda s: s.recipe.name)
    ])
    section("Machines", [
        f"**{count:,} ×** {_factory_link(machine, plan.machine_sources.get(machine))}"
        for machine, count in sorted(plan.machine_totals.items(), key=lambda pair: (-pair[1], pair[0]))
    ], size=8)

    from tools.factory_calculator import normalize
    consumers = {}
    for downstream in plan.stages:
        for ingredient, _quantity in downstream.recipe.ingredients:
            consumers.setdefault(normalize(ingredient), []).append(downstream.recipe.name)
    stage_rows = []
    for index, stage in enumerate(plan.stages, 1):
        recipe = stage.recipe
        final_output = recipe.path == plan.target.path
        heading = "Final output" if final_output else f"Stage {index}"
        count = f"{stage.machines:,}" if stage.machines is not None else "Unknown count"
        destinations = list(dict.fromkeys(consumers.get(normalize(recipe.name), [])))
        usage = ", ".join(discord.utils.escape_markdown(name) for name in destinations[:3])
        if len(destinations) > 3:
            usage += f" + {len(destinations) - 3} other stages"
        stage_rows.append(
            f"**{heading} ·** {_factory_link(recipe.name, recipe.source)}\n"
            f"Make **{rate(stage.required)} per minute total**\n"
            f"Use **{count} × {discord.utils.escape_markdown(recipe.machine or 'machine unknown')}**"
            + (f"\n-# Supplies: {usage}" if usage and not final_output else "")
        )
    section("Stages", stage_rows, size=3)
    notes = [
        "**How to read this plan**\nInput rates match your target. Rounded machines have spare capacity. "
        "Shared ingredient demand is combined before rounding.",
        "Machine totals cover ongoing production. Materials for constructing the machines are excluded.",
    ]
    notes.extend(
        f"**Machine placement**\n{_factory_link(machine, plan.machine_sources.get(machine))}: "
        f"{discord.utils.escape_markdown(placement)}"
        for machine, placement in plan.placements
    )
    if plan.issues:
        notes = ["**Missing wiki data**\n" + discord.utils.escape_markdown(issue)
                 for issue in dict.fromkeys(plan.issues)] + notes
    section("Notes", notes)
    return pages


def _factory_page_view(plan, pages, index):
    section = pages[index][0]
    siblings = [i for i, page in enumerate(pages) if page[0] == section]
    suffix = f" · {siblings.index(index) + 1}/{len(siblings)}" if len(siblings) > 1 else ""
    footer = (("Partial plan · see Notes. " if not plan.complete else "")
              + "Upstream parts first. Separate branches can run in parallel.") if section == "Stages" else (
                  "Partial plan · see Notes" if not plan.complete else "Capital Rift Wiki · All rates per minute")
    return build_card(
        f"{plan.target.name[:90]} · {section}{suffix}", pages[index][1],
        footer=footer, state="warning" if not plan.complete else "info",
    )



def build_factory_views(plan):
    """Return all detail views for validation; delivery starts with overview only."""
    pages = _factory_pages(plan)
    return [_factory_page_view(plan, pages, index) for index in range(len(pages))]


class FactoryPlanView(discord.ui.LayoutView):
    """Browse one factory result in place instead of posting a chain of messages."""
    def __init__(self, plan, *, pages=None, index=0):
        super().__init__(timeout=900)
        self.plan = plan
        self.pages = pages if pages is not None else _factory_pages(plan)
        self.index = index
        self.message = None
        base = _factory_page_view(plan, self.pages, index)
        for child in list(base.children):
            base.remove_item(child)
            self.add_item(child)
        section = self.pages[index][0]
        tabs = discord.ui.ActionRow()
        for name in dict.fromkeys(page[0] for page in self.pages):
            target = next(i for i, page in enumerate(self.pages) if page[0] == name)
            label = "Notes !" if name == "Notes" and not plan.complete else name
            button = discord.ui.Button(
                label=label, style=discord.ButtonStyle.primary if name == section else discord.ButtonStyle.secondary,
                disabled=name == section,
            )
            button.callback = self._navigate(target)
            tabs.add_item(button)
        self.add_item(tabs)
        siblings = [i for i, page in enumerate(self.pages) if page[0] == section]
        position = siblings.index(index)
        if len(siblings) > 1:
            controls = discord.ui.ActionRow()
            for label, offset in (("Previous", -1), ("Next", 1)):
                destination = position + offset
                disabled = not 0 <= destination < len(siblings)
                button = discord.ui.Button(label=label, disabled=disabled)
                button.callback = self._navigate(siblings[destination] if not disabled else index)
                controls.add_item(button)
            self.add_item(controls)

    def _navigate(self, index):
        async def callback(interaction):
            view = FactoryPlanView(self.plan, pages=self.pages, index=index)
            await interaction.response.edit_message(view=view, allowed_mentions=discord.AllowedMentions.none())
            view.message = interaction.message
            self.stop()
        return callback

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        self.add_item(discord.ui.TextDisplay("-# Controls expired. Run /factory again to browse this plan."))
        if self.message is not None:
            try:
                await self.message.edit(view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass


async def send_factory_plan(send, plan, *, ephemeral=None):
    view = FactoryPlanView(plan)
    kwargs = {"view": view, "allowed_mentions": discord.AllowedMentions.none()}
    if ephemeral is not None:
        kwargs["ephemeral"] = ephemeral
    view.message = await send(**kwargs)
    mark_delivery()
