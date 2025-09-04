from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    discord_token: Optional[str]
    openai_api_key: Optional[str]
    openrouter_api_key: Optional[str]
    plex_base_url: str
    plex_token: Optional[str]
    radarr_base_url: str
    radarr_api_key: Optional[str]
    sonarr_base_url: str
    sonarr_api_key: Optional[str]
    tmdb_api_key: Optional[str]
    discord_development_guild_id: Optional[str]
    application_id: Optional[str]


def load_settings(project_root: Path) -> Settings:
    env_path = project_root / ".env"
    load_dotenv(env_path)

    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        plex_base_url=os.getenv("PLEX_BASE_URL", "http://localhost:32400"),
        plex_token=os.getenv("PLEX_TOKEN"),
        radarr_base_url=os.getenv("RADARR_BASE_URL", "http://localhost:7878"),
        radarr_api_key=os.getenv("RADARR_API_KEY"),
        sonarr_base_url=os.getenv("SONARR_BASE_URL", "http://localhost:8989"),
        sonarr_api_key=os.getenv("SONARR_API_KEY"),
        tmdb_api_key=os.getenv("TMDB_API_KEY"),
        discord_development_guild_id=os.getenv("DISCORD_GUILD_ID"),
        application_id=os.getenv("APPLICATION_ID"),
    )


def load_runtime_config(project_root: Path) -> dict:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_llm_provider_and_model(project_root: Path, role: str, settings: Settings | None = None) -> tuple[str, str]:
    """Return (provider, model) for a given role: chat|smart|worker.

    Uses config.llm.providers.priority order and picks first provider that has
    required API key in Settings and defines a model for the role.
    """
    rc = load_runtime_config(project_root)
    providers_cfg = (rc.get("llm", {}) or {}).get("providers", {}) or {}
    priority = providers_cfg.get("priority") or []

    if settings is None:
        settings = load_settings(project_root)

    def has_api_key(p: str) -> bool:
        if p == "openai":
            return bool(settings.openai_api_key)
        if p == "openrouter":
            return bool(settings.openrouter_api_key)
        return False

    for p in priority:
        models = providers_cfg.get(p, {}) or {}
        model = models.get(role)
        if model and has_api_key(p):
            return p, str(model)

    # Fallbacks if priority missing or no key available
    # Prefer OpenAI if key exists
    if settings.openai_api_key:
        model = ((providers_cfg.get("openai", {}) or {}).get(role)) or (
            "gpt-5-mini" if role == "chat" else ("gpt-5" if role == "smart" else "gpt-5-nano")
        )
        return "openai", str(model)
    if settings.openrouter_api_key:
        model = ((providers_cfg.get("openrouter", {}) or {}).get(role)) or "z-ai/glm-4.5-air:free"
        return "openrouter", str(model)

    # Last resort defaults
    default = "gpt-5-mini" if role == "chat" else ("gpt-5" if role == "smart" else "gpt-5-nano")
    return "openai", default


def resolve_llm_selection(project_root: Path, role: str, settings: Settings | None = None) -> tuple[str, dict]:
    """Return (provider, selection) for a given role: chat|smart|worker.

    Selection is a dict with at least:
      - model: str
      - reasoningEffort: Optional[str] (minimal|medium|high)
      - params: dict[str, Any] of extra request params (e.g., temperature)

    Supports both legacy string config and new object config shape:
      llm.providers.PROVIDER.ROLE: "model-name" | { model, reasoningEffort?, params? }
    """
    rc = load_runtime_config(project_root)
    providers_cfg = (rc.get("llm", {}) or {}).get("providers", {}) or {}
    priority = providers_cfg.get("priority") or []

    if settings is None:
        settings = load_settings(project_root)

    def has_api_key(p: str) -> bool:
        if p == "openai":
            return bool(settings.openai_api_key)
        if p == "openrouter":
            return bool(settings.openrouter_api_key)
        return False

    def coerce_selection(raw: object) -> dict:
        # Allow string or dict; normalize to dict with keys model, reasoningEffort, params
        if isinstance(raw, str):
            return {"model": raw, "params": {}}
        if isinstance(raw, dict):
            model = raw.get("model") or raw.get("name") or raw.get("id")
            sel = {
                "model": str(model) if model else "",
                "reasoningEffort": raw.get("reasoningEffort"),
                "params": raw.get("params", {}),
            }
            # Merge top-level known params directly too (e.g., temperature) for convenience
            for k in ("temperature", "top_p", "max_tokens", "tool_choice"):
                if k in raw and k not in sel["params"]:
                    sel["params"][k] = raw[k]
            return sel
        return {"model": "", "params": {}}

    # Try providers in priority order
    for p in priority:
        models = providers_cfg.get(p, {}) or {}
        raw = models.get(role)
        if raw and has_api_key(p):
            sel = coerce_selection(raw)
            # Default reasoning effort for chat role if not specified
            if role == "chat" and "reasoningEffort" not in sel:
                sel["reasoningEffort"] = "minimal"
            return p, sel

    # Fallbacks if priority missing or no key available
    if settings.openai_api_key:
        raw = (providers_cfg.get("openai", {}) or {}).get(role)
        if not raw:
            # role-based defaults
            raw = "gpt-5-mini" if role == "chat" else ("gpt-5" if role == "smart" else "gpt-5-nano")
        sel = coerce_selection(raw)
        if role == "chat" and "reasoningEffort" not in sel:
            sel["reasoningEffort"] = "minimal"
        return "openai", sel
    if settings.openrouter_api_key:
        raw = (providers_cfg.get("openrouter", {}) or {}).get(role) or "z-ai/glm-4.5-air:free"
        sel = coerce_selection(raw)
        if role == "chat" and "reasoningEffort" not in sel:
            sel["reasoningEffort"] = "minimal"
        return "openrouter", sel

    # Last resort defaults
    default_model = "gpt-5-mini" if role == "chat" else ("gpt-5" if role == "smart" else "gpt-5-nano")
    sel = {"model": default_model, "reasoningEffort": "minimal" if role == "chat" else None, "params": {}}
    return "openai", sel


def is_config_complete(settings: Settings, runtime_config: dict) -> bool:
    required_env = [
        settings.discord_token,
        settings.openai_api_key,
        settings.plex_token,
        settings.radarr_api_key,
        settings.sonarr_api_key,
        settings.tmdb_api_key,
    ]
    if any(v is None or str(v).strip() == "" for v in required_env):
        return False

    # Require Radarr/Sonarr defaults to be present for smoother UX
    radarr_ok = bool(runtime_config.get("radarr", {}).get("qualityProfileId")) and bool(
        runtime_config.get("radarr", {}).get("rootFolderPath")
    )
    sonarr_ok = bool(runtime_config.get("sonarr", {}).get("qualityProfileId")) and bool(
        runtime_config.get("sonarr", {}).get("rootFolderPath")
    )
    return radarr_ok and sonarr_ok

