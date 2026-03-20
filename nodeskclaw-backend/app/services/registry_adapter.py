"""Registry Adapter abstract interface and unified data types.

Defines the contract that all skill registry adapters must implement,
plus shared Pydantic models for cross-registry data exchange.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field


class RegistrySkillItem(BaseModel):
    """Unified skill item returned by any adapter's search / featured."""

    slug: str
    name: str
    description: str | None = None
    short_description: str | None = None
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    source: str = "official"
    source_ref: str | None = None
    icon: str | None = None
    install_count: int = 0
    avg_rating: float = 0.0
    effectiveness_score: float = 0.0
    is_featured: bool = False
    review_status: str | None = None
    is_published: bool = True
    manifest: dict | None = None
    dependencies: list[str] = Field(default_factory=list)
    synergies: list[str] = Field(default_factory=list)
    parent_gene_id: str | None = None
    created_by_instance_id: str | None = None
    created_by: str | None = None
    org_id: str | None = None
    visibility: str = "public"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    source_registry: str = ""
    source_registry_name: str = ""

    local_id: str | None = None


class RegistrySearchResult(BaseModel):
    """Paginated search result from a single adapter."""

    items: list[RegistrySkillItem] = Field(default_factory=list)
    total: int = 0


class RegistrySkillDetail(RegistrySkillItem):
    """Extended detail (currently identical to item; reserved for future fields)."""

    pass


class RegistryAdapter(ABC):
    """Abstract base class for skill registry adapters."""

    registry_id: str
    registry_name: str
    base_url: str | None

    def __init__(
        self,
        *,
        registry_id: str,
        registry_name: str,
        base_url: str | None = None,
    ) -> None:
        self.registry_id = registry_id
        self.registry_name = registry_name
        self.base_url = base_url

    @abstractmethod
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
        ...

    @abstractmethod
    async def get_skill(self, slug: str) -> RegistrySkillDetail | None:
        ...

    @abstractmethod
    async def get_manifest(self, slug: str, version: str | None = None) -> dict | None:
        ...

    @abstractmethod
    async def get_featured(self, limit: int = 10) -> list[RegistrySkillItem] | None:
        ...

    @abstractmethod
    async def get_tags(self) -> list[dict] | None:
        ...

    @abstractmethod
    async def get_synergies(self, slug: str) -> list[dict] | None:
        ...

    @abstractmethod
    async def publish_skill(self, manifest: dict) -> dict | None:
        ...

    @abstractmethod
    async def report_install(self, slug: str) -> bool:
        ...

    @abstractmethod
    async def report_effectiveness(
        self, slug: str, metric_type: str, value: float
    ) -> bool:
        ...

    async def close(self) -> None:
        """Shutdown underlying connections. Default no-op."""
        pass
