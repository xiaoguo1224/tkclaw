from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    HTTPS_PROXY: str = ""
    LLM_LOG_CONTENT: bool = False
    CODEX_COMMAND: str = "codex"
    CODEX_HOME: str = ""
    CODEX_SKIP_GIT_REPO_CHECK: bool = True
    CODEX_BYPASS_APPROVALS_AND_SANDBOX: bool = False
    CODEX_TIMEOUT_SECONDS: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
