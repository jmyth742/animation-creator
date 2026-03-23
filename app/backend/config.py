"""Application configuration via Pydantic BaseSettings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "changeme-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    DATABASE_URL: str = "sqlite:///./storybuilder.db"
    WORKSPACE_ROOT: Path = Path("/workspace/text-to-video")

    # ── Computed path properties ──────────────────────────────────────────

    @property
    def SERIES_DIR(self) -> Path:
        return self.WORKSPACE_ROOT / "series"

    @property
    def OUTPUT_DIR(self) -> Path:
        return self.WORKSPACE_ROOT / "output"

    @property
    def COMFYUI_DIR(self) -> Path:
        return self.WORKSPACE_ROOT / "ComfyUI"

    @property
    def COMFYUI_OUTPUT(self) -> Path:
        return self.COMFYUI_DIR / "output" / "video"

    @property
    def COMFYUI_INPUT(self) -> Path:
        return self.COMFYUI_DIR / "input"

    @property
    def AMBIENCE_DIR(self) -> Path:
        return self.WORKSPACE_ROOT / "ambience"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
