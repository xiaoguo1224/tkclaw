from app.schemas.llm import ModelInfo

# SYNC: 以下三个常量与 nodeskclaw-llm-proxy/app/codex_cli.py 保持同步
CODEX_PROVIDER = "codex"
CODEX_CLI_SENTINEL = "__CODEX_CLI__"

CODEX_MODELS: list[ModelInfo] = [
    ModelInfo(id="gpt-5.4", name="gpt-5.4"),
    ModelInfo(id="gpt-5.3-codex", name="gpt-5.3-codex"),
    ModelInfo(id="gpt-5.3-codex-spark", name="gpt-5.3-codex-spark"),
    ModelInfo(id="gpt-5", name="gpt-5"),
    ModelInfo(id="o3", name="o3"),
    ModelInfo(id="o4-mini", name="o4-mini"),
    ModelInfo(id="gpt-5-mini", name="gpt-5-mini"),
    ModelInfo(id="gpt-5-nano", name="gpt-5-nano"),
    ModelInfo(id="o3-mini", name="o3-mini"),
    ModelInfo(id="codex-mini-latest", name="Codex Mini"),
]


def is_codex_provider(provider: str) -> bool:
    return provider == CODEX_PROVIDER


def is_codex_cli_sentinel(api_key: str | None) -> bool:
    return (api_key or "").strip() == CODEX_CLI_SENTINEL


def normalize_codex_api_key(api_key: str | None) -> str:
    if api_key and api_key.strip():
        return api_key
    return CODEX_CLI_SENTINEL


def get_default_codex_model() -> dict:
    return CODEX_MODELS[0].model_dump(exclude_none=True)


def normalize_selected_models(provider: str, selected_models: list[dict] | None) -> list[dict] | None:
    if selected_models:
        return selected_models
    if is_codex_provider(provider):
        return [get_default_codex_model()]
    return selected_models


def mask_personal_key(provider: str, api_key: str) -> str:
    if is_codex_provider(provider) and is_codex_cli_sentinel(api_key):
        return "Codex CLI"
    if len(api_key) <= 8:
        return api_key[:2] + "***"
    return api_key[:6] + "***" + api_key[-3:]
