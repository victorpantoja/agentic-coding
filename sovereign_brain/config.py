"""Application settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://sovereign:sovereign@localhost:5432/sovereign_brain"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
