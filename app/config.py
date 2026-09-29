from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "website-filter"
    app_env: str = "dev"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    admin_api_key: str = ""

    allow_threshold: float = 0.90
    block_threshold: float = 0.90
    policy_version: str = "1.0"

    allow_ttl: int = 86400
    block_ttl: int = 21600
    review_ttl: int = 1800

    redis_url: str = "redis://localhost:6379/0"

    sqlite_path: str = "./data/website_filter.db"

    fetch_timeout_s: float = 8.0
    fetch_connect_timeout_s: float = 3.0
    fetch_max_bytes: int = 1_000_000
    fetch_max_redirects: int = 3
    fetch_user_agent: str = "website-filter/1.0 (+internal IT use)"

    jev_api_url: str = ""
    jev_api_key: str = ""
    jev_model_version: str = "1.x"
    jev_timeout_ms: int = 5000
    jev_mode: str = "auto"  # auto | api | heuristic


settings = Settings()
