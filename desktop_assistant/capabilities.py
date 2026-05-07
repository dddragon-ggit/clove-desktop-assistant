from __future__ import annotations

from .capability.defaults import _default_capabilities
from .capability.models import CapabilityDefinition
from .capability.registry import CapabilityRegistry
from .capability.validation import SHELL_LIKE_APP_MARKERS, _risk_rank, max_risk

DEFAULT_CAPABILITY_REGISTRY = CapabilityRegistry.default()

__all__ = [
    "CapabilityDefinition",
    "CapabilityRegistry",
    "DEFAULT_CAPABILITY_REGISTRY",
    "SHELL_LIKE_APP_MARKERS",
    "max_risk",
    "_default_capabilities",
    "_risk_rank",
]
