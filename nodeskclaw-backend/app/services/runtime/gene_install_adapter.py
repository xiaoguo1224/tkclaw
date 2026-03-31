"""GeneInstallAdapter -- abstract interface for runtime-specific gene installation logic.

Each AI runtime (OpenClaw, NanoBot) implements its own adapter to handle:
- Skill file deployment
- Tool availability (e.g. OpenClaw's tool_allow whitelist)
- Python script deployment
- Cache invalidation / hot-reload triggers
- Skill removal on uninstall
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.nfs_mount import RemoteFS

logger = logging.getLogger(__name__)


class GeneInstallAdapter(ABC):
    """Runtime-specific gene installation adapter."""

    @abstractmethod
    async def deploy_skill(
        self, fs: RemoteFS, skill_name: str, content: str, description: str = "",
    ) -> None:
        """Deploy a skill file to the runtime's skill directory."""

    @abstractmethod
    async def allow_tools(self, fs: RemoteFS, tool_names: list[str]) -> None:
        """Make tools immediately available in the runtime (no-op for runtimes without whitelisting)."""

    @abstractmethod
    async def deploy_scripts(self, fs: RemoteFS, scripts: dict[str, str]) -> None:
        """Deploy executable Python scripts to the instance.

        Args:
            fs: Remote filesystem handle.
            scripts: Mapping of filename -> script content.
        """

    @abstractmethod
    async def apply_config(self, fs: RemoteFS, config_patch: dict) -> None:
        """Apply runtime-specific configuration patches."""

    @abstractmethod
    async def invalidate_cache(self, fs: RemoteFS, skill_name: str, event: str = "installed") -> None:
        """Invalidate runtime caches after installation and notify the agent."""

    @abstractmethod
    async def remove_skill(self, fs: RemoteFS, skill_name: str) -> None:
        """Remove a skill on uninstall."""

    @abstractmethod
    async def post_remove_cleanup(self, fs: RemoteFS, skill_name: str) -> None:
        """Post-removal cleanup: cache invalidation and uninstall notification."""
