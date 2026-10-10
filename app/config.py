import os
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()


class Settings(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    debug: bool = False
    node_id: str = "the-banished-local"

    # Proxmox
    proxmox_host: str = "the-banished"
    proxmox_port: int = 8006
    proxmox_user: str = "root@pam!build-token"
    proxmox_token: str = ""
    proxmox_node: str = "the-banished"
    proxmox_verify_ssl: bool = False

    # AI Diagnostics
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    @classmethod
    def from_environment(cls) -> "Settings":
        raw_debug = os.getenv("DEBUG", "false").strip().casefold()
        return cls(
            host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "8080")),
            debug=raw_debug in {"true", "1", "yes", "on"},
            node_id=os.getenv("NODE_ID", "the-banished-local"),
            proxmox_host=os.getenv("PROXMOX_HOST", "the-banished"),
            proxmox_port=int(os.getenv("PROXMOX_PORT", "8006")),
            proxmox_user=os.getenv("PROXMOX_USER", "root@pam!build-token"),
            proxmox_token=os.getenv("PROXMOX_TOKEN", ""),
            proxmox_node=os.getenv("PROXMOX_NODE", "the-banished"),
            proxmox_verify_ssl=os.getenv("PROXMOX_VERIFY_SSL", "false").lower() in ("true", "1"),
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        )


settings = Settings.from_environment()