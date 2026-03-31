"""Registry Aggregator — module-level singleton for multi-source queries.

Usage:
    from app.services.registry_aggregator import init, get_aggregator, close

    # Startup (in main.py lifespan)
    init([local_adapter, deskhub_adapter, ...])

    # Service layer
    agg = get_aggregator()
    result = await agg.search(keyword="git")

    # Shutdown
    await close()
"""

from __future__ import annotations

import asyncio
import logging

from app.services.registry_adapter import (
    RegistryAdapter,
    RegistrySearchResult,
    RegistrySkillDetail,
    RegistrySkillItem,
)

logger = logging.getLogger(__name__)

_PRIORITY = ["local", "deskhub", "genehub", "clawhub"]

_aggregator: RegistryAggregator | None = None


class RegistryAggregator:
    """Orchestrates parallel queries to multiple RegistryAdapters."""

    def __init__(self, adapters: list[RegistryAdapter]) -> None:
        self._adapters = {a.registry_id: a for a in adapters}
        self._ordered = adapters
        logger.info(
            "RegistryAggregator initialised with adapters: %s",
            [a.registry_id for a in adapters],
        )

    @property
    def adapter_ids(self) -> list[str]:
        return [a.registry_id for a in self._ordered]

    def get_adapter(self, registry_id: str) -> RegistryAdapter | None:
        return self._adapters.get(registry_id)

    # ── search / read ──

    async def search(
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
    ) -> RegistrySearchResult:
        tasks = [
            a.search_skills(
                keyword=keyword,
                tag=tag,
                category=category,
                source=source,
                visibility=visibility,
                org_id=org_id,
                sort=sort,
                page=page,
                page_size=page_size,
            )
            for a in self._ordered
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_slugs: dict[str, int] = {}
        merged: list[RegistrySkillItem] = []
        total = 0

        for adapter, result in zip(self._ordered, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Adapter %s search failed: %s", adapter.registry_id, result
                )
                continue
            if result is None:
                continue
            total += result.total
            for item in result.items:
                priority = self._priority_of(adapter.registry_id)
                existing_idx = seen_slugs.get(item.slug)
                if existing_idx is not None:
                    existing_priority = self._priority_of(
                        merged[existing_idx].source_registry
                    )
                    if priority < existing_priority:
                        merged[existing_idx] = item
                else:
                    seen_slugs[item.slug] = len(merged)
                    merged.append(item)

        return RegistrySearchResult(items=merged, total=total)

    async def get_skill(self, slug: str) -> RegistrySkillDetail | None:
        for adapter in self._sorted_adapters():
            try:
                detail = await adapter.get_skill(slug)
                if detail is not None:
                    return detail
            except Exception as e:
                logger.warning(
                    "Adapter %s get_skill(%s) failed: %s",
                    adapter.registry_id, slug, e,
                )
        return None

    async def get_manifest(self, slug: str, version: str | None = None) -> dict | None:
        for adapter in self._sorted_adapters():
            try:
                manifest = await adapter.get_manifest(slug, version)
                if manifest is not None:
                    return manifest
            except Exception as e:
                logger.warning(
                    "Adapter %s get_manifest(%s) failed: %s",
                    adapter.registry_id, slug, e,
                )
        return None

    async def get_featured(self, limit: int = 10) -> list[RegistrySkillItem]:
        tasks = [a.get_featured(limit) for a in self._ordered]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_slugs: set[str] = set()
        merged: list[RegistrySkillItem] = []

        for adapter, result in zip(self._ordered, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Adapter %s get_featured failed: %s", adapter.registry_id, result
                )
                continue
            if not result:
                continue
            for item in result:
                if item.slug not in seen_slugs:
                    seen_slugs.add(item.slug)
                    merged.append(item)

        merged.sort(key=lambda x: x.install_count, reverse=True)
        return merged[:limit]

    async def get_tags(self) -> list[dict]:
        tasks = [a.get_tags() for a in self._ordered]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        tag_counts: dict[str, int] = {}
        for adapter, result in zip(self._ordered, results):
            if isinstance(result, Exception) or not result:
                continue
            for entry in result:
                tag = entry.get("tag", "")
                count = entry.get("count", 0)
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + count

        return [
            {"tag": k, "count": v}
            for k, v in sorted(tag_counts.items(), key=lambda x: -x[1])
        ]

    async def get_synergies(self, slug: str) -> list[dict] | None:
        for adapter in self._sorted_adapters():
            try:
                synergies = await adapter.get_synergies(slug)
                if synergies is not None:
                    return synergies
            except Exception as e:
                logger.warning(
                    "Adapter %s get_synergies(%s) failed: %s",
                    adapter.registry_id, slug, e,
                )
        return None

    # ── write-back routing ──

    async def publish_to(self, registry_id: str, manifest: dict) -> dict | None:
        adapter = self._adapters.get(registry_id)
        if not adapter:
            logger.warning("publish_to: unknown registry_id=%s", registry_id)
            return None
        try:
            return await adapter.publish_skill(manifest)
        except Exception as e:
            logger.warning(
                "publish_to(%s) failed: %s", registry_id, e
            )
            return None

    async def report_install_to(self, registry_id: str, slug: str) -> bool:
        adapter = self._adapters.get(registry_id)
        if not adapter:
            return False
        try:
            return await adapter.report_install(slug)
        except Exception as e:
            logger.warning(
                "report_install_to(%s, %s) failed: %s", registry_id, slug, e
            )
            return False

    async def report_effectiveness_to(
        self, registry_id: str, slug: str, metric_type: str, value: float
    ) -> bool:
        adapter = self._adapters.get(registry_id)
        if not adapter:
            return False
        try:
            return await adapter.report_effectiveness(slug, metric_type, value)
        except Exception as e:
            logger.warning(
                "report_effectiveness_to(%s, %s) failed: %s", registry_id, slug, e
            )
            return False

    async def close_all(self) -> None:
        for adapter in self._ordered:
            try:
                await adapter.close()
            except Exception as e:
                logger.warning("Error closing adapter %s: %s", adapter.registry_id, e)

    # ── internal ──

    def _priority_of(self, registry_id: str) -> int:
        try:
            return _PRIORITY.index(registry_id)
        except ValueError:
            return len(_PRIORITY)

    def _sorted_adapters(self) -> list[RegistryAdapter]:
        return sorted(self._ordered, key=lambda a: self._priority_of(a.registry_id))


# ═══════════════════════════════════════════════════
#  Module-level singleton API
# ═══════════════════════════════════════════════════


def init(adapters: list[RegistryAdapter]) -> None:
    global _aggregator
    _aggregator = RegistryAggregator(adapters)


def get_aggregator() -> RegistryAggregator:
    if _aggregator is None:
        raise RuntimeError(
            "RegistryAggregator not initialised — call registry_aggregator.init() first"
        )
    return _aggregator


async def close() -> None:
    global _aggregator
    if _aggregator:
        await _aggregator.close_all()
        _aggregator = None
