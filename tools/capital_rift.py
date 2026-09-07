"""Obsidian wiki retrieval and deterministic production-line calculations."""
import json
import math
import os
from pathlib import Path

from knowledge.obsidian_vault import ObsidianVaultIndex, VaultError

_WIKI_INDEX = None

WIKI_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "capital_rift_wiki",
        "description": (
            "Search or read the locally configured Capital Rift Obsidian wiki. "
            "Use this before answering questions about Capital Rift mechanics, "
            "items, buildings, recipes, factories, or production chains."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "read", "status"],
                },
                "query": {
                    "type": "string",
                    "description": "Keywords or question for a wiki search.",
                },
                "note_path": {
                    "type": "string",
                    "description": "Exact relative Markdown path returned by search.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}

PRODUCTION_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_production_line",
        "description": (
            "Perform deterministic production-line math using recipe values first "
            "verified in the Capital Rift wiki. Calculates machines, output, and "
            "ingredient rates. Never guess recipe values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recipe_name": {"type": "string"},
                "source_note": {
                    "type": "string",
                    "description": "Wiki note path supporting the recipe values.",
                },
                "target_output_per_minute": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "output_per_cycle": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "cycle_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "machine_speed_multiplier": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "default": 1,
                },
                "planned_utilization": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 1,
                    "default": 1,
                },
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "amount_per_cycle": {
                                "type": "number",
                                "minimum": 0,
                            },
                        },
                        "required": ["name", "amount_per_cycle"],
                        "additionalProperties": False,
                    },
                    "default": [],
                },
            },
            "required": [
                "recipe_name",
                "source_note",
                "target_output_per_minute",
                "output_per_cycle",
                "cycle_seconds",
            ],
            "additionalProperties": False,
        },
    },
}


def _response(action: str, data) -> str:
    return json.dumps(
        {
            "source": "Local Capital Rift Obsidian vault",
            "readOnly": True,
            "action": action,
            "data": data,
        },
        separators=(",", ":"),
        allow_nan=False,
    )


def _get_wiki_index() -> ObsidianVaultIndex:
    global _WIKI_INDEX
    if _WIKI_INDEX is not None:
        return _WIKI_INDEX

    vault_path = (
        os.environ.get("CAPITAL_RIFT_VAULT_PATH", "").strip()
        or os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    )
    if not vault_path:
        raise VaultError("CAPITAL_RIFT_VAULT_PATH (or legacy OBSIDIAN_VAULT_PATH) is not configured on the bot host.")

    default_index = Path(__file__).resolve().parent.parent / "data" / "capital_rift_wiki.db"
    index_path = os.environ.get("CAPITAL_RIFT_INDEX_PATH", "").strip() or str(default_index)
    _WIKI_INDEX = ObsidianVaultIndex(
        vault_path,
        index_path,
        refresh_seconds=float(os.environ.get("CAPITAL_RIFT_VAULT_REFRESH_SECONDS", "30")),
        max_note_bytes=int(os.environ.get("CAPITAL_RIFT_MAX_NOTE_BYTES", str(2 * 1024 * 1024))),
    )
    return _WIKI_INDEX


async def capital_rift_wiki(
    action: str,
    query: str | None = None,
    note_path: str | None = None,
    limit: int = 5,
) -> str:
    try:
        index = _get_wiki_index()
        if action == "search":
            if not query:
                return _response(action, {"error": "A search query is required."})
            results = await index.search(query, limit=limit)
            return _response(
                action,
                {
                    "query": query,
                    "results": [
                        {
                            "path": item.path,
                            "title": item.title,
                            "excerpt": item.excerpt,
                            "relevanceScore": item.score,
                        }
                        for item in results
                    ],
                },
            )

        if action == "read":
            if not note_path:
                return _response(action, {"error": "A note_path from search is required."})
            return _response(action, await index.read_note(note_path))

        if action == "status":
            status = await index.status()
            return _response(
                action,
                {
                    "configured": True,
                    "totalNotes": status["totalNotes"],
                    "readOnlyVault": True,
                },
            )

        return _response(action, {"error": f"Unsupported wiki action: {action}"})
    except VaultError as exc:
        return _response(action, {"configured": False, "error": str(exc)})
    except OSError:
        return _response(
            action,
            {"configured": False, "error": "The configured wiki vault could not be read."},
        )


def _number(value, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be a finite number.") from None
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        bound = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field} must be finite and {bound}.")
    return number


def _normalize_ingredients(ingredients) -> list[dict]:
    if ingredients is None:
        return []
    if isinstance(ingredients, str):
        try:
            ingredients = json.loads(ingredients)
        except ValueError:
            raise ValueError("ingredients must be an array or a JSON-encoded array.") from None
    if not isinstance(ingredients, list):
        raise ValueError("ingredients must be an array of ingredient objects.")
    normalized = []
    for ingredient in ingredients:
        if not isinstance(ingredient, dict):
            raise ValueError("Every ingredient must be an object with name and amount_per_cycle.")
        name = ingredient.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every ingredient needs a non-empty string name.")
        amount = _number(ingredient.get("amount_per_cycle"), "amount_per_cycle", allow_zero=True)
        normalized.append({"name": name.strip(), "amount_per_cycle": amount})
    return normalized


async def calculate_production_line(
    recipe_name: str,
    source_note: str,
    target_output_per_minute: float,
    output_per_cycle: float,
    cycle_seconds: float,
    machine_speed_multiplier: float = 1,
    planned_utilization: float = 1,
    ingredients: list[dict] | str | None = None,
) -> str:
    """Calculate rates from supplied facts; this function performs no AI estimation."""
    target_output_per_minute = _number(target_output_per_minute, "target_output_per_minute")
    output_per_cycle = _number(output_per_cycle, "output_per_cycle")
    cycle_seconds = _number(cycle_seconds, "cycle_seconds")
    machine_speed_multiplier = _number(machine_speed_multiplier, "machine_speed_multiplier")
    planned_utilization = _number(planned_utilization, "planned_utilization")
    if planned_utilization > 1:
        raise ValueError("Planned utilization must be greater than 0 and at most 1.")
    if not isinstance(source_note, str) or not source_note.strip():
        raise ValueError("A supporting wiki source note is required.")
    if not isinstance(recipe_name, str) or not recipe_name.strip():
        raise ValueError("A recipe name is required.")
    source_note = source_note.strip()
    recipe_name = recipe_name.strip()
    ingredients = _normalize_ingredients(ingredients)
    cycles_per_minute = (
        60.0 / float(cycle_seconds)
        * float(machine_speed_multiplier)
        * float(planned_utilization)
    )
    output_per_machine = float(output_per_cycle) * cycles_per_minute
    _number(output_per_machine, "Calculated output per machine")
    exact_machines = float(target_output_per_minute) / output_per_machine
    _number(exact_machines, "Calculated machine count")
    machines_required = max(1, math.ceil(exact_machines - 1e-12))
    full_output = machines_required * output_per_machine
    target_cycles_per_minute = float(target_output_per_minute) / float(output_per_cycle)

    ingredient_rates = []
    for ingredient in ingredients:
        name = ingredient["name"]
        amount = ingredient["amount_per_cycle"]
        ingredient_rates.append(
            {
                "name": name,
                "requiredAtTargetPerMinute": amount * target_cycles_per_minute,
                "fullCapacityPerMinute": amount * cycles_per_minute * machines_required,
            }
        )

    return json.dumps(
        {
            "calculation": "Capital Rift production line",
            "deterministic": True,
            "recipeName": recipe_name,
            "sourceNote": source_note,
            "inputs": {
                "targetOutputPerMinute": float(target_output_per_minute),
                "outputPerCycle": float(output_per_cycle),
                "cycleSeconds": float(cycle_seconds),
                "machineSpeedMultiplier": float(machine_speed_multiplier),
                "plannedUtilization": float(planned_utilization),
            },
            "result": {
                "cyclesPerMachinePerMinute": cycles_per_minute,
                "outputPerMachinePerMinute": output_per_machine,
                "exactMachines": exact_machines,
                "machinesRequired": machines_required,
                "outputAtFullCapacityPerMinute": full_output,
                "surplusPerMinute": full_output - float(target_output_per_minute),
                "ingredients": ingredient_rates,
            },
        },
        separators=(",", ":"),
        allow_nan=False,
    )
