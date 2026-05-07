from __future__ import annotations

from pathlib import Path


def default_recipe_store_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "recipes.json"


def default_recipe_name(user_goal: str) -> str:
    compact = " ".join(user_goal.split())
    return compact[:32] or "Untitled recipe"


def normalize_recipe_query(value: str) -> str:
    return " ".join(value.lower().split())


def extract_refinement_constraints(user_refinement: str) -> list[str]:
    constraints: list[str] = []
    for raw_line in user_refinement.replace("；", "\n").replace(";", "\n").splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue
        lowered = line.lower()
        if any(marker in lowered for marker in ["不要", "别", "不需要", "改成", "instead", "without", "do not", "don't"]):
            constraints.append(line)
    if constraints:
        return constraints
    return [user_refinement.strip()] if user_refinement.strip() else []


_default_recipe_name = default_recipe_name
_normalize = normalize_recipe_query
_extract_refinement_constraints = extract_refinement_constraints
