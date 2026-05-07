from __future__ import annotations

from .models import (
    ACTIVITY_LOG_SCHEMA_VERSION,
    ActivityApp,
    ActivityFile,
    ActivityProject,
    ActivitySnapshot,
    ActivityWindow,
)
from .process import NullProcessMetadataProvider, ProcessMetadataProviderProtocol, WindowsProcessMetadataProvider
from .privacy import (
    ACTIVITY_PRIVACY_SCHEMA_VERSION,
    ActivityPrivacySettings,
    ActivityPrivacyStore,
    apply_activity_privacy,
    clear_activity_records,
    default_activity_privacy_path,
)
from .recent_files import RecentFileProviderProtocol, StaticRecentFileProvider, WindowsRecentFileProvider
from .resolver import ActivityResolver
from .sampler import DesktopActivitySampler
from .store import ActivityStore, default_activity_log_path

__all__ = [
    "ACTIVITY_LOG_SCHEMA_VERSION",
    "ActivityApp",
    "ActivityFile",
    "ActivityProject",
    "ActivityResolver",
    "ActivitySnapshot",
    "ActivityStore",
    "ActivityWindow",
    "ActivityPrivacySettings",
    "ActivityPrivacyStore",
    "ACTIVITY_PRIVACY_SCHEMA_VERSION",
    "DesktopActivitySampler",
    "NullProcessMetadataProvider",
    "ProcessMetadataProviderProtocol",
    "RecentFileProviderProtocol",
    "StaticRecentFileProvider",
    "WindowsProcessMetadataProvider",
    "WindowsRecentFileProvider",
    "default_activity_log_path",
    "default_activity_privacy_path",
    "apply_activity_privacy",
    "clear_activity_records",
]
