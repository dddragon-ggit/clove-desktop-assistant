from __future__ import annotations

from collections.abc import Callable

from ..capabilities import CapabilityRegistry
from .models import RecipeCheckIssue, RecipeCheckResult, WorkflowRecipe


def check_recipe(
    recipe: WorkflowRecipe,
    *,
    capability_registry: CapabilityRegistry | None = None,
    available_handler_names: set[str] | None = None,
    path_exists: Callable[[str], bool] | None = None,
) -> RecipeCheckResult:
    registry = capability_registry or CapabilityRegistry.default()
    issues: list[RecipeCheckIssue] = []
    for index, step in enumerate(recipe.plan.steps, start=1):
        capability = registry.get(step.action_type)
        if capability is None:
            issues.append(
                RecipeCheckIssue(
                    severity="error",
                    code="ACTION_NOT_REGISTERED",
                    message=f"Action {step.action_type.value} is not registered.",
                    step_index=index,
                )
            )
            continue
        if capability.execution_mode == "disabled":
            issues.append(
                RecipeCheckIssue(
                    severity="error",
                    code="CAPABILITY_DISABLED",
                    message=f"Capability {step.action_type.value} is disabled.",
                    step_index=index,
                )
            )
        if (
            available_handler_names is not None
            and capability.handler_name
            and capability.handler_name != "simulated"
            and capability.handler_name not in available_handler_names
        ):
            issues.append(
                RecipeCheckIssue(
                    severity="error",
                    code="HANDLER_MISSING",
                    message=f"Handler {capability.handler_name} is not available.",
                    step_index=index,
                )
            )
        for policy_issue in registry.validate_action(step):
            issues.append(
                RecipeCheckIssue(
                    severity="error",
                    code=policy_issue.code,
                    message=policy_issue.message,
                    step_index=index,
                )
            )
        if path_exists is not None and step.action_type.value in {"open_folder", "open_file"}:
            target = step.target.strip()
            if target and not path_exists(target):
                issues.append(
                    RecipeCheckIssue(
                        severity="warning",
                        code="PATH_MISSING",
                        message=f"Path target does not currently exist: {target}",
                        step_index=index,
                    )
                )
    return RecipeCheckResult(
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )
