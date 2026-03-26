"""RuntimeConfigAdapter — abstracts config file I/O and channel translation per runtime."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.utils.jsonc import strip_jsonc

if TYPE_CHECKING:
    from app.models.instance import Instance
    from app.services.nfs_mount import RemoteFS
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RuntimeConfigAdapter(ABC):
    @abstractmethod
    async def read_config(self, fs: RemoteFS) -> dict | None:
        """Read the full config file. Returns None if not found."""
        ...

    @abstractmethod
    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        """Write the full config file."""
        ...

    @abstractmethod
    def extract_channels(self, config: dict) -> dict:
        """Extract the channels section from the full config."""
        ...

    @abstractmethod
    def merge_channels(self, config: dict, channels: dict) -> dict:
        """Merge channel configs back into the full config, returning the updated config."""
        ...

    @abstractmethod
    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        """Restart the runtime instance after config changes."""
        ...

    @abstractmethod
    def supported_channels(self) -> list[str]:
        """Return list of channel IDs this runtime supports."""
        ...

    @abstractmethod
    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        """Translate canonical (camelCase) field names to runtime-native keys."""
        ...

    @abstractmethod
    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        """Translate runtime-native keys to canonical (camelCase) field names."""
        ...


class OpenClawConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".openclaw/openclaw.json"

    async def read_config(self, fs: RemoteFS) -> dict | None:
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(strip_jsonc(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"openclaw.json 格式无法解析: {e}") from e

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        await fs.write_text(
            self._CONFIG_REL,
            json.dumps(data, indent=2, ensure_ascii=False),
        )

    def extract_channels(self, config: dict) -> dict:
        return config.get("channels", {})

    def merge_channels(self, config: dict, channels: dict) -> dict:
        config["channels"] = channels

        plugins = config.setdefault("plugins", {})
        entries = plugins.setdefault("entries", {})
        for cid in channels:
            entries[cid] = {"enabled": True}
        return config

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        from app.services.llm_config_service import restart_runtime
        return await restart_runtime(instance, db)

    def supported_channels(self) -> list[str]:
        return [
            "feishu", "dingtalk", "telegram", "discord", "slack", "whatsapp",
            "irc", "signal", "googlechat", "msteams", "matrix",
            "mattermost", "bluebubbles", "nextcloud-talk", "imessage",
            "line", "nostr", "tlon", "twitch", "synology-chat",
            "zalo", "zalouser",
        ]

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        return canonical

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        return native


class NanobotConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".nanobot/config.json"

    async def read_config(self, fs: RemoteFS) -> dict | None:
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"nanobot config.json 格式无法解析: {e}") from e

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        await fs.write_text(
            self._CONFIG_REL,
            json.dumps(data, indent=2, ensure_ascii=False),
        )

    def extract_channels(self, config: dict) -> dict:
        return config.get("channels", {})

    def merge_channels(self, config: dict, channels: dict) -> dict:
        config["channels"] = channels
        return config

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        return await _restart_container(instance, db)

    def supported_channels(self) -> list[str]:
        return [
            "feishu", "telegram", "discord", "slack", "matrix",
            "whatsapp", "email", "dingtalk", "qq", "wecom", "mochat",
        ]

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return canonical
        result: dict = {}
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("nanobot")
            if runtime_key and field_def.key in canonical:
                result[runtime_key] = canonical[field_def.key]
        for k, v in canonical.items():
            if not any(f.key == k for f in defn.fields):
                result[k] = v
        return result

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return native
        result: dict = {}
        reverse_map: dict[str, str] = {}
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("nanobot")
            if runtime_key:
                reverse_map[runtime_key] = field_def.key
        for k, v in native.items():
            result[reverse_map.get(k, k)] = v
        return result


class ZeroClawConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".zeroclaw/config.toml"

    async def read_config(self, fs: RemoteFS) -> dict | None:
        import tomllib
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            return tomllib.loads(raw)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"zeroclaw config.toml 格式无法解析: {e}") from e

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        import tomli_w
        await fs.write_text(
            self._CONFIG_REL,
            tomli_w.dumps(data),
        )

    def extract_channels(self, config: dict) -> dict:
        return config.get("channels_config", {})

    def merge_channels(self, config: dict, channels: dict) -> dict:
        config["channels_config"] = channels
        return config

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        return await _restart_container(instance, db)

    def supported_channels(self) -> list[str]:
        return [
            "feishu", "telegram", "discord", "slack", "matrix",
            "whatsapp", "email", "dingtalk", "qq", "signal", "irc",
            "mattermost", "imessage", "nextcloud-talk", "webhook",
            "linq", "nostr",
        ]

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return _camel_to_snake_dict(canonical)
        result: dict = {}
        for field in defn.fields:
            runtime_key = field.runtime_key.get("zeroclaw")
            if runtime_key and field.key in canonical:
                result[runtime_key] = canonical[field.key]
        for k, v in canonical.items():
            if not any(f.key == k for f in defn.fields):
                result[_camel_to_snake(k)] = v
        return result

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return _snake_to_camel_dict(native)
        result: dict = {}
        reverse_map = {}
        for field in defn.fields:
            runtime_key = field.runtime_key.get("zeroclaw")
            if runtime_key:
                reverse_map[runtime_key] = field.key
        for k, v in native.items():
            result[reverse_map.get(k, _snake_to_camel(k))] = v
        return result


def _camel_to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _camel_to_snake_dict(d: dict) -> dict:
    return {_camel_to_snake(k): v for k, v in d.items()}


def _snake_to_camel_dict(d: dict) -> dict:
    return {_snake_to_camel(k): v for k, v in d.items()}


async def _restart_container(instance: Instance, db: AsyncSession) -> dict:
    """Generic container restart for NanoBot / ZeroClaw (SIGTERM + wait)."""
    if instance.compute_provider == "docker":
        from app.services.instance_service import _build_docker_handle, _get_docker_provider
        try:
            provider = _get_docker_provider()
            handle = _build_docker_handle(instance)
            await provider.restart_instance(handle)
            return {"status": "ok", "message": "重启完成"}
        except Exception as e:
            logger.error("Docker 实例 %s 重启失败: %s", instance.name, e)
            return {"status": "error", "message": f"Docker 重启失败: {e}"}

    import asyncio
    from app.services.nfs_mount import _get_k8s_client, _k8s_name

    k8s = await _get_k8s_client(instance, db)
    deploy_name = _k8s_name(instance)

    from app.services.nfs_mount import _find_running_pod
    try:
        pod_name, container = await _find_running_pod(k8s, instance)
        await k8s.exec_in_pod(
            instance.namespace, pod_name,
            ["kill", "-SIGTERM", "1"],
            container=container,
        )
        logger.info("已发送 SIGTERM 到实例 %s 的 PID 1", instance.name)
    except Exception as e:
        logger.warning("exec kill 失败，降级为 Deployment 滚动重启: %s", e)
        await k8s.restart_deployment(instance.namespace, deploy_name)

    for _ in range(30):
        await asyncio.sleep(2)
        pods = await k8s.list_pods(
            instance.namespace,
            f"app.kubernetes.io/name={deploy_name}",
        )
        running = [p for p in pods if p["phase"] == "Running"]
        if running:
            for p in running:
                ready = all(c.get("ready", False) for c in p.get("containers", []))
                if ready:
                    return {"status": "ok", "message": "重启完成"}

    return {"status": "timeout", "message": "重启超时（60s），请检查实例状态"}


_ADAPTERS: dict[str, RuntimeConfigAdapter] = {
    "openclaw": OpenClawConfigAdapter(),
    "nanobot": NanobotConfigAdapter(),
    "zeroclaw": ZeroClawConfigAdapter(),
}


def get_config_adapter(runtime: str) -> RuntimeConfigAdapter:
    adapter = _ADAPTERS.get(runtime)
    if adapter is None:
        raise ValueError(f"不支持的 runtime: {runtime}")
    return adapter
