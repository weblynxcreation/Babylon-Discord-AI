"""Wiki-only recursive production planning. No model or network calls."""
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
import re
from pathlib import PurePosixPath

from wiki_cards import split_wiki_metadata, https_url

MAX_NODES = 256
MAX_DEPTH = 64
RATE_RE = re.compile(
    r"(?<![\w.])(?P<amount>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*"
    r"(?P<item>[A-Za-z][A-Za-z -]*?\s*)?"
    r"(?:\bper\s+|/\s*)(?P<unit>minutes?|mins?|hours?|hrs?)\b", re.I
)


class FactoryError(ValueError):
    pass


def number(value):
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise FactoryError("Missing or invalid positive wiki quantity/rate.") from None
    if result <= 0:
        raise FactoryError("Missing or invalid positive wiki quantity/rate.")
    return result


def normalize(name):
    name = name.split("|")[0].split("#")[0].strip("[] ")
    name = PurePosixPath(name.removesuffix(".md")).name
    return re.sub(r"[^\w]+", " ", name.casefold()).strip()


def full_factory_request(text):
    return bool(RATE_RE.search(text) or re.search(
        r"\b(?:full\s+(?:factory|production\s+chain|chain)|(?:from\s+)?raw\s+(?:components?|materials?))\b", text, re.I))


@dataclass(frozen=True)
class FactoryRequest:
    item: str
    rate: Fraction | None


def parse_factory_request(text):
    matches = list(RATE_RE.finditer(text))
    if len(matches) > 1:
        raise FactoryError("Specify one target output rate per request.")
    rate = None
    if matches:
        match = matches[0]
        rate = number(match["amount"])
        if match["unit"].casefold().startswith(("h",)):
            rate /= 60
        if rate > 1000000:
            raise FactoryError("Use a target of at most 1,000,000 units/min.")
        text = text[:match.start()] + " " + (match["item"] or "") + " " + text[match.end():]
    text = re.sub(r"\bfacotry\b", "factory", text, flags=re.I)
    text = re.sub(
        r"\b(how|do|can|i|you|me|make|build|create|a|an|the|factory|full|"
        r"production|chain|line|setup|set|up|plan|for|to|of|in|at|please|"
        r"capable|produce|producing|from|raw|components?|materials?|output|"
        r"units?|per|minute|hour)\b", " ", text, flags=re.I)
    text = re.sub(r"[^\w -]", " ", text)
    item = re.sub(r"\s+", " ", text).strip()
    if not item:
        raise FactoryError("Specify the item to produce.")
    return FactoryRequest(item, rate)


@dataclass
class Recipe:
    name: str
    path: str = ""
    source: str | None = None
    machine: str | None = None
    output: Fraction | None = None
    rate: Fraction | None = None
    ingredients: list = field(default_factory=list)
    has_recipe: bool = False
    raw: bool = False
    issues: list = field(default_factory=list)
    placement: str | None = None


def parse_recipe(note):
    metadata, body = split_wiki_metadata(note.get("content"))
    name = metadata.get("name") or note.get("title") or PurePosixPath(note["path"]).stem
    recipe = Recipe(name, note["path"], https_url(metadata.get("source")))
    recipe.placement = metadata.get("placement")
    if not recipe.source:
        recipe.issues.append("Public wiki source link missing.")
    body = re.split(r"^## (?:Source|Personal notes)\s*$", body, maxsplit=1, flags=re.M)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    sections = re.findall(r"^## Recipe\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    recipe.has_recipe = bool(sections or any(key.startswith("recipe_") for key in metadata))
    if note.get("truncated"):
        recipe.issues.append("Wiki note truncated; upstream data cannot be calculated.")
        recipe.has_recipe = True
        return recipe
    if not recipe.has_recipe:
        # A recipe-less page is an external input, never silently assumed mineable.
        description = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        recipe.raw = bool(re.search(r"\braw\b|\bdug from a surveyed deposit\b", description, re.I))
        if not recipe.raw:
            recipe.issues.append("No recipe published; acquisition/raw-material status unverified.")
        return recipe
    recipe.machine = metadata.get("recipe_machine", "").strip('"\'[] ') or None
    if recipe.machine:
        recipe.machine = recipe.machine.split("|")[0].split("#")[0]
    else:
        recipe.issues.append("Recipe machine missing.")
    for key, attr in (("recipe_output_quantity", "output"), ("recipe_rate_per_minute", "rate")):
        try:
            setattr(recipe, attr, number(metadata.get(key)))
        except FactoryError:
            recipe.issues.append(f"{key} missing or invalid.")
    section = sections[0] if len(sections) == 1 else ""
    # Do not choose an arbitrary alternative recipe or mix ingredient tables.
    if len(re.findall(r"^### ", section, re.M)) > 1 or len(sections) > 1:
        recipe.issues.append("Multiple recipes; an explicit recipe selection is required.")
        recipe.rate = recipe.output = None
        return recipe
    tables = re.findall(r"^#### Ingredients\s*\n(.*?)(?=^#{1,4} |\Z)", section, re.M | re.S)
    if len(tables) != 1:
        recipe.issues.append("Ingredient quantities missing or ambiguous.")
        return recipe
    rows = [line.strip() for line in tables[0].splitlines() if line.strip().startswith("|")]
    ingredients = []
    valid = len(rows) >= 3 and bool(re.match(r"^\|\s*Quantity\s*\|\s*Item\s*\|", rows[0], re.I))
    for row in rows[2:]:
        # Preserve aliases inside [[Item|label]], which are not table delimiters.
        protected = re.sub(r"\[\[([^\]]+)\]\]", lambda m: "[[" + m[1].replace("|", "\x00") + "]]", row)
        cells = [cell.strip().replace("\x00", "|") for cell in protected.strip("|").split("|")]
        try:
            if len(cells) < 2:
                raise FactoryError("Invalid ingredient row.")
            quantity = number(cells[0])
            reference = re.fullmatch(r"\[\[([^\]]+)\]\]", cells[1])
            if not reference:
                raise FactoryError("Ingredient wiki reference missing.")
            ingredients.append((reference[1].split("|")[0].split("#")[0], quantity))
        except FactoryError:
            valid = False
    if valid and ingredients:
        recipe.ingredients = ingredients
    else:
        recipe.issues.append("Ingredient table incomplete or invalid; upstream rates unavailable.")
    return recipe


class RecipeBook:
    def __init__(self, notes):
        self.by_name = defaultdict(list)
        self.recipes = {}
        for note in notes:
            recipe = parse_recipe(note)
            self.recipes[recipe.path] = recipe
            for key in {normalize(recipe.name), normalize(recipe.path)}:
                self.by_name[key].append(recipe)

    def resolve(self, name, *, plural=False):
        key = normalize(name)
        matches = self.by_name.get(key, [])
        if not matches and plural and key.endswith("s"):
            matches = self.by_name.get(key[:-1], [])
        if len(matches) > 1:
            raise FactoryError(f"Ambiguous wiki item: {name}.")
        return matches[0] if matches else None


@dataclass
class Stage:
    recipe: Recipe
    required: Fraction
    machines: int | None


@dataclass
class FactoryPlan:
    target: Recipe
    rate: Fraction
    stages: list
    inputs: list
    machine_totals: dict
    machine_sources: dict
    placements: list
    issues: list

    @property
    def complete(self):
        return not self.issues


def calculate_factory(notes, request):
    book = RecipeBook(notes)
    target = book.resolve(request.item, plural=True)
    if target is None:
        raise FactoryError(f"No exact wiki item named {request.item} was found.")
    if request.rate is None:
        raise FactoryError("Specify a scale, such as 1 per minute or 10 per hour.")
    target_rate = number(request.rate)
    visiting, visited, order, edges = set(), set(), [], {}
    issues = []

    def visit(recipe, depth):
        key = recipe.path or normalize(recipe.name)
        if key in visiting:
            raise FactoryError(f"Recipe cycle detected at {recipe.name}; no valid full-chain totals can be calculated.")
        if key in visited:
            return
        if depth > MAX_DEPTH or len(visited) + len(visiting) >= MAX_NODES:
            raise FactoryError("Production chain exceeds the calculation limit; choose a smaller chain.")
        visiting.add(key)
        edges[key] = []
        issues.extend(f"{recipe.name}: {issue}" for issue in recipe.issues)
        if recipe.has_recipe and recipe.output and recipe.ingredients:
            for name, quantity in recipe.ingredients:
                child = book.resolve(name)
                if child is None:
                    child = Recipe(name, issues=["Wiki note/recipe missing; input acquisition unverified."])
                visit(child, depth + 1)
                edges[key].append((child.path or normalize(child.name), quantity / recipe.output))
        visiting.remove(key)
        visited.add(key)
        order.append((key, recipe))

    visit(target, 0)
    demand = defaultdict(Fraction)
    demand[target.path] = target_rate
    stages, inputs, totals, sources, placements = [], [], defaultdict(int), {}, []
    for key, recipe in reversed(order):
        required = demand[key]
        if recipe.has_recipe:
            machines = None
            if recipe.rate and recipe.machine:
                ratio = required / recipe.rate
                machines = -(-ratio.numerator // ratio.denominator)
                totals[recipe.machine] += machines
            stages.append(Stage(recipe, required, machines))
        else:
            inputs.append(Stage(recipe, required, None))
        for child, ratio in edges[key]:
            demand[child] += required * ratio
    # Display upstream stages first. Each shared recipe is rounded only once.
    stages.reverse()
    for machine in totals:
        try:
            note = book.resolve(machine)
        except FactoryError:
            note = None
        sources[machine] = note.source if note else None
        if not sources[machine]:
            issues.append(f"{machine}: machine wiki source link missing.")
        if note and note.placement:
            placements.append((machine, note.placement))
    return FactoryPlan(target, target_rate, stages, inputs, dict(totals), sources, placements, issues)


async def plan_factory(request):
    from tools.capital_rift import _get_wiki_index
    notes = await _get_wiki_index().snapshot_notes()
    return calculate_factory(notes, request)
