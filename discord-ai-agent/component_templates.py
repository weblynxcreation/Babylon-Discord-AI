"""Load and render the bot's shared Discord Components V2 templates."""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


DEFAULT_VAULT_ROOT = Path(__file__).with_name("Babylon Bot Templates")
VAULT_ROOT = Path(
    os.environ.get("BABYLON_TEMPLATE_VAULT", DEFAULT_VAULT_ROOT)
).expanduser()
TEMPLATE_FILES = {
    "item": VAULT_ROOT / "Templates" / "Item Command.md",
    "moderation_automod_timeout": VAULT_ROOT / "Moderation" / "Automod Timeout.md",
    "moderation_incident": VAULT_ROOT / "Templates" / "Moderation Incident.md",
    "moderation_manual_action": VAULT_ROOT / "Moderation" / "Moderator Action.md",
    "moderation_message_deleted": VAULT_ROOT / "Moderation" / "Message Deleted.md",
    "moderation_permission_error": VAULT_ROOT / "Moderation" / "Permission Error.md",
    "moderation_raid_detected": VAULT_ROOT / "Moderation" / "Raid Detected.md",
    "moderation_raid_join_action": VAULT_ROOT / "Moderation" / "Raid Join Action.md",
    "production_line": VAULT_ROOT / "Templates" / "Production Line.md",
}

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{([a-zA-Z][a-zA-Z0-9_]*)\}\}")


class ComponentTemplateError(ValueError):
    """Raised when a shared component template cannot be loaded or rendered."""


def load_template_payload(template_name: str) -> dict[str, Any]:
    """Read the Components V2 JSON payload embedded in an Obsidian note."""
    try:
        path = TEMPLATE_FILES[template_name]
    except KeyError as exc:
        raise ComponentTemplateError(f"Unknown component template: {template_name}") from exc

    try:
        note = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ComponentTemplateError(f"Could not read component template: {path}") from exc

    match = _JSON_FENCE.search(note)
    if match is None:
        raise ComponentTemplateError(f"Template has no JSON payload: {path}")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ComponentTemplateError(f"Template contains invalid JSON: {path}") from exc
    if payload.get("flags") != 32768 or not isinstance(payload.get("components"), list):
        raise ComponentTemplateError(
            f"Template must enable Components V2 and contain components: {path}"
        )
    return payload


def template_placeholders(template_name: str) -> set[str]:
    """Return the placeholder names required by a template."""
    payload = load_template_payload(template_name)
    return set(_PLACEHOLDER.findall(json.dumps(payload)))


def render_template_payload(
    template_name: str,
    values: Mapping[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Replace {{placeholder}} tokens without mutating the source payload."""
    payload = copy.deepcopy(load_template_payload(template_name))
    missing: set[str] = set()

    def render(value: Any) -> Any:
        if isinstance(value, str):
            whole_placeholder = _PLACEHOLDER.fullmatch(value)
            if whole_placeholder:
                key = whole_placeholder.group(1)
                source_value = values.get(key)
                if (
                    key not in values
                    or source_value is None
                    or (isinstance(source_value, str) and not source_value.strip())
                ):
                    missing.add(key)
                    return value
                return source_value

            def replace(match: re.Match[str]) -> str:
                key = match.group(1)
                source_value = values.get(key)
                if (
                    key not in values
                    or source_value is None
                    or (isinstance(source_value, str) and not source_value.strip())
                ):
                    missing.add(key)
                    return match.group(0)
                return str(source_value)

            return _PLACEHOLDER.sub(replace, value)
        if isinstance(value, list):
            return [render(item) for item in value]
        if isinstance(value, dict):
            return {key: render(item) for key, item in value.items()}
        return value

    rendered = render(payload)
    if strict and missing:
        names = ", ".join(sorted(missing))
        raise ComponentTemplateError(f"Missing template values: {names}")
    return rendered


def build_layout_view(template_name: str, values: Mapping[str, Any]):
    """Build a discord.py 2.6+ LayoutView from a shared static template."""
    import discord

    payload = render_template_payload(template_name, values)
    view = discord.ui.LayoutView()
    for component in payload["components"]:
        view.add_item(_build_component(discord, component))
    return view


def _build_component(discord: Any, component: Mapping[str, Any]):
    component_type = component.get("type")
    if component_type == 10:
        return discord.ui.TextDisplay(component["content"])
    if component_type == 11:
        return discord.ui.Thumbnail(
            component["media"]["url"],
            description=component.get("description"),
            spoiler=component.get("spoiler", False),
        )
    if component_type == 14:
        spacing = (
            discord.SeparatorSpacing.large
            if component.get("spacing", 1) == 2
            else discord.SeparatorSpacing.small
        )
        return discord.ui.Separator(
            visible=component.get("divider", True),
            spacing=spacing,
        )
    if component_type == 9:
        children = [_build_component(discord, child) for child in component["components"]]
        accessory = _build_component(discord, component["accessory"])
        return discord.ui.Section(*children, accessory=accessory)
    if component_type == 17:
        children = [_build_component(discord, child) for child in component["components"]]
        return discord.ui.Container(
            *children,
            accent_color=component.get("accent_color"),
            spoiler=component.get("spoiler", False),
        )
    raise ComponentTemplateError(f"Unsupported component type: {component_type}")
