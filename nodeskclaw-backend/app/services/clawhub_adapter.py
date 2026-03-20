"""ClawHub Registry adapter — stub implementation.

All methods return None / False / empty to prove architectural extensibility.
Fill in real HTTP calls after ClawHub API verification.
"""

from __future__ import annotations

from app.services.registry_adapter import (
    RegistryAdapter,
    RegistrySearchResult,
    RegistrySkillDetail,
    RegistrySkillItem,
)


class ClawHubAdapter(RegistryAdapter):
    """Stub adapter for clawhub.ai — all ops are no-ops until API is verified."""

    def __init__(
        self,
        *,
        registry_id: str = "clawhub",
        registry_name: str = "ClawHub",
        base_url: str = "https://clawhub.ai",
        api_key: str = "",
    ) -> None:
        super().__init__(
            registry_id=registry_id,
            registry_name=registry_name,
            base_url=base_url,
        )
        self._api_key = api_key

    async def search_skills(
        self,
        *,
        keyword: str | None = None,
        tag: str | None = None,
        category: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        org_id: str | None = None,
        sort: str = "popularity",
        page: int = 1,
        page_size: int = 20,
    ) -> RegistrySearchResult | None:
        return None

    async def get_skill(self, slug: str) -> RegistrySkillDetail | None:
        return None

    async def get_manifest(self, slug: str, version: str | None = None) -> dict | None:
        return None

    async def get_featured(self, limit: int = 10) -> list[RegistrySkillItem] | None:
        return None

    async def get_tags(self) -> list[dict] | None:
        return None

    async def get_synergies(self, slug: str) -> list[dict] | None:
        return None

    async def publish_skill(self, manifest: dict) -> dict | None:
        return None

    async def report_install(self, slug: str) -> bool:
        return False

    async def report_effectiveness(
        self, slug: str, metric_type: str, value: float
    ) -> bool:
        return False
