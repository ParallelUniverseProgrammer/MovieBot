from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
import curses
import textwrap
import webbrowser
import getpass


def _prompt(key: str, default: str | None = None, secret: bool = False) -> str:
    label = f"{key}"
    if not secret and default:
        label += f" [{default}]"
    label += ": "
    if secret:
        value = getpass.getpass(label)
    else:
        value = input(label)
    if (value is None or value == "") and default is not None:
        return default
    return value.strip()


def _load_env_file(project_root: Path) -> Dict[str, str]:
    """Load key=value pairs from .env, ignoring comments and preserving simple values.

    Does not modify the environment. Handles optional 'export ' prefix and ignores blank lines.
    """
    env_values: Dict[str, str] = {}
    env_path = project_root / ".env"
    if not env_path.exists():
        return env_values
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :]
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_values[k.strip()] = v.strip()
    except Exception:
        # Be permissive: if parsing fails, just return what we have
        pass
    return env_values


def _write_env(project_root: Path, env_updates: Dict[str, str]) -> Tuple[bool, Path | None, Path | None]:
    """Safely persist env values.

    Returns (written, env_path_if_written, suggested_path_if_not_written).
    - If .env exists: DO NOT MODIFY. Writes suggestions to .env.wizard.suggested and returns (False, None, suggest_path).
    - If .env does not exist: Creates it with provided values and returns (True, env_path, None).
    Empty values are ignored.
    """
    env_path = project_root / ".env"
    filtered: Dict[str, str] = {k: v for k, v in env_updates.items() if isinstance(v, str) and v.strip() != ""}
    if env_path.exists():
        # Never overwrite existing .env; provide a suggested file instead
        if not filtered:
            return (False, None, None)
        suggest_path = project_root / ".env.wizard.suggested"
        with open(suggest_path, "w", encoding="utf-8") as f:
            for k, v in filtered.items():
                f.write(f"{k}={v}\n")
        return (False, None, suggest_path)
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in filtered.items():
                f.write(f"{k}={v}\n")
        return (True, env_path, None)


def _write_config(project_root: Path, config_obj: Dict[str, Any]) -> None:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_obj, f, sort_keys=True)


def _write_household_prefs(project_root: Path) -> None:
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    prefs_path = data_dir / "household_preferences.json"
    if not prefs_path.exists():
        seed = {
            "version": 1,
            "profile": {
                "baseFlavor": "Sleek, twisty, recent English-language genre; hidden gems; claustro bonus; plausibility ~8/10",
                "anchors": {
                    "loved": ["The Matrix", "The Art of Self-Defense", "Greener Grass", "Late Night with the Devil", "Fresh", "Mickey 17"],
                    "responded": ["The Outfit"],
                    "comfortSignals": ["The Life Aquatic"],
                    "trustedFaces": ["Pedro Pascal", "Margot Robbie"],
                },
                "curiosities": ["possession/cult", "home/urban invasion", "social-tech paranoia", "tech dystopia", "polyamory"],
            },
            "likes": {"genres": [], "people": [], "languages": ["en"]},
            "dislikes": {"genres": ["found footage"], "aesthetics": ["shaky-cam", "drab grime"]},
            "constraints": {"eraMinYear": 2019, "runtimeSweetSpotMins": [100, 130]},
            "neverRecommend": {"tmdbIds": [], "titles": []},
            "notes": "Household advanced preference profile; tools should read subsets on demand."
        }
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(seed, f, indent=2)


def run_interactive(project_root: Path) -> None:
    try:
        _run_curses_wizard(project_root)
        return
    except Exception as e:  # noqa: BLE001
        print("Curses wizard unavailable, falling back to simple prompts. Reason:", e)

    print("MovieBot setup wizard (fallback)\n")

    # Prefill from existing .env without modifying it
    existing_env = _load_env_file(project_root)

    print("Discord")
    discord_token = _prompt("DISCORD_TOKEN", default=existing_env.get("DISCORD_TOKEN"), secret=True)
    application_id = _prompt("APPLICATION_ID (from Discord Developer Portal)", default=existing_env.get("APPLICATION_ID", ""))
    dev_guild = _prompt("DISCORD_GUILD_ID (dev guild, optional)", default=existing_env.get("DISCORD_GUILD_ID", ""))

    print("\nOpenAI")
    openai_key = _prompt("OPENAI_API_KEY", default=existing_env.get("OPENAI_API_KEY"), secret=True)

    print("\nPlex")
    plex_base = _prompt("PLEX_BASE_URL", default=existing_env.get("PLEX_BASE_URL", "http://localhost:32400"))
    plex_token = _prompt("PLEX_TOKEN", default=existing_env.get("PLEX_TOKEN"), secret=True)

    print("\nRadarr")
    radarr_base = _prompt("RADARR_BASE_URL", default=existing_env.get("RADARR_BASE_URL", "http://localhost:7878"))
    radarr_key = _prompt("RADARR_API_KEY", default=existing_env.get("RADARR_API_KEY"), secret=True)

    print("\nSonarr")
    sonarr_base = _prompt("SONARR_BASE_URL", default=existing_env.get("SONARR_BASE_URL", "http://localhost:8989"))
    sonarr_key = _prompt("SONARR_API_KEY", default=existing_env.get("SONARR_API_KEY"), secret=True)

    print("\nTMDb")
    tmdb_key = _prompt("TMDB_API_KEY", default=existing_env.get("TMDB_API_KEY"), secret=True)

    # Only write keys that are missing or changed vs existing .env
    desired_env: Dict[str, str] = {
        "DISCORD_TOKEN": discord_token,
        "APPLICATION_ID": application_id,
        "DISCORD_GUILD_ID": dev_guild,
        "OPENAI_API_KEY": openai_key,
        "PLEX_BASE_URL": plex_base,
        "PLEX_TOKEN": plex_token,
        "RADARR_BASE_URL": radarr_base,
        "RADARR_API_KEY": radarr_key,
        "SONARR_BASE_URL": sonarr_base,
        "SONARR_API_KEY": sonarr_key,
        "TMDB_API_KEY": tmdb_key,
    }
    diff_env = {k: v for k, v in desired_env.items() if v is not None and v != "" and existing_env.get(k) != v}
    env_written, env_path, suggest_path = _write_env(project_root, diff_env)

    print("\nFetching Radarr/Sonarr defaults requires API calls; you can set them later in config/config.yaml.")
    radarr_profile_id = _prompt("Default Radarr qualityProfileId (e.g. 1)", default="")
    radarr_root_folder = _prompt("Default Radarr rootFolderPath (e.g. /data/movies)", default="")
    sonarr_profile_id = _prompt("Default Sonarr qualityProfileId (e.g. 1)", default="")
    sonarr_root_folder = _prompt("Default Sonarr rootFolderPath (e.g. /data/tv)", default="")

    config_obj: Dict[str, Any] = {
        "household": {"displayName": "Household"},
        "radarr": {
            "qualityProfileId": int(radarr_profile_id) if radarr_profile_id else None,
            "rootFolderPath": radarr_root_folder or None,
        },
        "sonarr": {
            "qualityProfileId": int(sonarr_profile_id) if sonarr_profile_id else None,
            "rootFolderPath": sonarr_root_folder or None,
        },
    }
    _write_config(project_root, config_obj)
    _write_household_prefs(project_root)

    if env_written:
        print("\nSaved .env, config/config.yaml, and data/household_preferences.json")
    elif suggest_path is not None:
        print(f"\nSaved config/config.yaml and data/household_preferences.json. Existing .env left untouched. Suggestions written to: {suggest_path}")
    else:
        print("\nSaved config/config.yaml and data/household_preferences.json. Existing .env left untouched.")
    print("Next: invite your Discord bot to a server and run: python -m bot.discord_bot")


# ---------------- Curses-based TUI -----------------

def _run_curses_wizard(project_root: Path) -> None:
    curses.wrapper(lambda stdscr: _Wizard(project_root).run(stdscr))


class _Wizard:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.env_values: Dict[str, str] = {}
        self.config_values: Dict[str, Any] = {
            "radarr": {"qualityProfileId": None, "rootFolderPath": None},
            "sonarr": {"qualityProfileId": None, "rootFolderPath": None},
        }
        self.steps = self._build_steps()
        self.step_index = 0
        self.field_index = 0

    def run(self, stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        curses.curs_set(1)
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_CYAN, 0)
            curses.init_pair(2, curses.COLOR_GREEN, 0)
            curses.init_pair(3, curses.COLOR_YELLOW, 0)
            curses.init_pair(4, curses.COLOR_MAGENTA, 0)
            curses.init_pair(5, curses.COLOR_RED, 0)
        self._prefill_from_env()
        while True:
            stdscr.clear()
            self._draw_header(stdscr)
            self._draw_step(stdscr)
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord('q'), 27):
                raise KeyboardInterrupt
            elif ch in (ord('n'), curses.KEY_RIGHT, 10):
                if self._can_advance():
                    if self.step_index < len(self.steps) - 1:
                        self.step_index += 1
                        self.field_index = 0
                    else:
                        self._save()
                        self._draw_done(stdscr)
                        stdscr.getch()
                        return
            elif ch in (ord('b'), curses.KEY_LEFT):
                if self.step_index > 0:
                    self.step_index -= 1
                    self.field_index = 0
            elif ch in (9, curses.KEY_DOWN):  # Tab or down
                self._next_field()
            elif ch in (curses.KEY_UP,):
                self._prev_field()
            elif ch == ord('o'):
                self._open_primary_link()
            elif ch == ord('h'):
                self._toggle_help()
            else:
                self._handle_text_input(ch)

    def _build_steps(self) -> List[Dict[str, Any]]:
        wrap = textwrap.fill
        return [
            {
                "key": "welcome",
                "title": "Welcome to MovieBot",
                "help": "This wizard will guide you to collect tokens and URLs needed to connect Discord, OpenAI, Plex, Radarr, Sonarr, and TMDb.",
                "links": [("Project README", "https://github.com/")],
                "fields": [],
            },
            {
                "key": "discord",
                "title": "Discord Bot",
                "help": (
                    "1) Create an application and bot in Discord Developer Portal.\n"
                    "2) Copy the Bot Token and Application ID.\n"
                    "3) (Optional) Provide a development Guild ID to sync slash commands quickly.\n"
                    "Portal: https://discord.com/developers/applications"
                ),
                "links": [("Discord Developer Portal", "https://discord.com/developers/applications")],
                "fields": [
                    {"env": "DISCORD_TOKEN", "label": "Bot Token", "secret": True},
                    {"env": "APPLICATION_ID", "label": "Application ID", "secret": False},
                    {"env": "DISCORD_GUILD_ID", "label": "Dev Guild ID (optional)", "secret": False, "optional": True},
                ],
            },
            {
                "key": "openai",
                "title": "OpenAI API",
                "help": (
                    "Get an API key to use GPT-5 models.\n"
                    "Link: https://platform.openai.com/api-keys"
                ),
                "links": [("OpenAI API Keys", "https://platform.openai.com/api-keys")],
                "fields": [
                    {"env": "OPENAI_API_KEY", "label": "OpenAI API Key", "secret": True},
                ],
            },
            {
                "key": "plex",
                "title": "Plex Server",
                "help": (
                    "Ensure MovieBot runs on the same machine/network as Plex.\n"
                    "Plex token guide: https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/"
                ),
                "links": [("Plex Token Guide", "https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/")],
                "fields": [
                    {"env": "PLEX_BASE_URL", "label": "Base URL", "secret": False, "default": "http://localhost:32400"},
                    {"env": "PLEX_TOKEN", "label": "Plex Token", "secret": True},
                ],
            },
            {
                "key": "radarr",
                "title": "Radarr",
                "help": (
                    "Find API Key in Radarr: Settings → General → Security.\n"
                    "Docs: https://wiki.servarr.com/radarr"
                ),
                "links": [("Radarr Docs", "https://wiki.servarr.com/radarr")],
                "fields": [
                    {"env": "RADARR_BASE_URL", "label": "Base URL", "secret": False, "default": "http://localhost:7878"},
                    {"env": "RADARR_API_KEY", "label": "API Key", "secret": True},
                ],
            },
            {
                "key": "sonarr",
                "title": "Sonarr",
                "help": (
                    "Find API Key in Sonarr: Settings → General → Security.\n"
                    "Docs: https://wiki.servarr.com/sonarr"
                ),
                "links": [("Sonarr Docs", "https://wiki.servarr.com/sonarr")],
                "fields": [
                    {"env": "SONARR_BASE_URL", "label": "Base URL", "secret": False, "default": "http://localhost:8989"},
                    {"env": "SONARR_API_KEY", "label": "API Key", "secret": True},
                ],
            },
            {
                "key": "tmdb",
                "title": "TMDb",
                "help": (
                    "Create a (free) API key for movie discovery and recommendations.\n"
                    "Link: https://www.themoviedb.org/settings/api"
                ),
                "links": [("TMDb API", "https://www.themoviedb.org/settings/api")],
                "fields": [
                    {"env": "TMDB_API_KEY", "label": "TMDb API Key", "secret": True},
                ],
            },
            {
                "key": "defaults",
                "title": "Defaults (optional)",
                "help": (
                    "You can set default profiles and root folders now or later in config/config.yaml.\n"
                    "Fetch actual IDs from Radarr/Sonarr UI (Profiles/Media Management)."
                ),
                "links": [],
                "fields": [
                    {"config": ("radarr", "qualityProfileId"), "label": "Radarr qualityProfileId", "secret": False, "optional": True},
                    {"config": ("radarr", "rootFolderPath"), "label": "Radarr rootFolderPath", "secret": False, "optional": True},
                    {"config": ("sonarr", "qualityProfileId"), "label": "Sonarr qualityProfileId", "secret": False, "optional": True},
                    {"config": ("sonarr", "rootFolderPath"), "label": "Sonarr rootFolderPath", "secret": False, "optional": True},
                ],
            },
            {
                "key": "summary",
                "title": "Summary",
                "help": "Press n to save and finish. Press b to go back and edit.",
                "links": [],
                "fields": [],
            },
        ]

    def _prefill_from_env(self) -> None:
        self.env_values.update(_load_env_file(self.project_root))

    def _draw_header(self, stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        h, w = stdscr.getmaxyx()
        step_num = self.step_index + 1
        total = len(self.steps)
        title = f"MovieBot Setup  —  Step {step_num}/{total}"
        stdscr.attron(curses.color_pair(1))
        stdscr.addstr(0, 1, title[: max(0, w - 2)])
        stdscr.attroff(curses.color_pair(1))
        # Progress bar
        progress_w = max(10, w - len(title) - 6)
        filled = int(progress_w * step_num / total)
        bar = "[" + ("#" * filled).ljust(progress_w, "-") + "]"
        stdscr.addstr(0, max(1, w - len(bar) - 1), bar)

    def _draw_step(self, stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        h, w = stdscr.getmaxyx()
        step = self.steps[self.step_index]
        y = 2
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(y, 2, step["title"][: w - 4])
        stdscr.attroff(curses.A_BOLD)
        y += 1
        # Help box
        help_text = step.get("help", "")
        for line in textwrap.wrap(help_text, width=max(20, w - 4)):
            stdscr.addstr(y, 2, line)
            y += 1
        links: List[Tuple[str, str]] = step.get("links", [])
        for name, url in links:
            stdscr.attron(curses.color_pair(3))
            stdscr.addstr(y, 2, f"- {name}: ")
            stdscr.attroff(curses.color_pair(3))
            stdscr.attron(curses.color_pair(4))
            stdscr.addstr(f"{url}")
            stdscr.attroff(curses.color_pair(4))
            y += 1
        y += 1

        fields: List[Dict[str, Any]] = step.get("fields", [])
        for idx, field in enumerate(fields):
            label = field["label"]
            is_active = idx == self.field_index
            value = self._get_field_value(field)
            display = ("*" * len(value)) if field.get("secret") and value else value
            prefix = "> " if is_active else "  "
            stdscr.addstr(y, 4, f"{prefix}{label}: {display}")
            y += 1

        # Footer
        y = h - 3
        try:
            stdscr.hline(y, 0, curses.ACS_HLINE, w)
        except Exception:
            stdscr.hline(y, 0, ord('-'), w)
        y += 1
        stdscr.addstr(y, 2, "Keys: n=next  b=back  o=open link  h=toggle help  q=quit")

    def _get_field_value(self, field: Dict[str, Any]) -> str:
        if "env" in field:
            key = field["env"]
            if key in self.env_values:
                return self.env_values[key]
            default = field.get("default")
            return default if default is not None else ""
        elif "config" in field:
            group, sub = field["config"]
            val = self.config_values.get(group, {}).get(sub)
            return "" if val is None else str(val)
        return ""

    def _set_field_value(self, field: Dict[str, Any], new_value: str) -> None:
        if "env" in field:
            self.env_values[field["env"]] = new_value
        elif "config" in field:
            group, sub = field["config"]
            if group not in self.config_values:
                self.config_values[group] = {}
            # Cast numeric profile IDs if possible
            if sub.endswith("qualityProfileId") and new_value.strip().isdigit():
                self.config_values[group][sub] = int(new_value.strip())
            else:
                self.config_values[group][sub] = new_value.strip() or None

    def _next_field(self) -> None:
        fields = self.steps[self.step_index].get("fields", [])
        if not fields:
            return
        self.field_index = (self.field_index + 1) % len(fields)

    def _prev_field(self) -> None:
        fields = self.steps[self.step_index].get("fields", [])
        if not fields:
            return
        self.field_index = (self.field_index - 1) % len(fields)

    def _open_primary_link(self) -> None:
        links = self.steps[self.step_index].get("links", [])
        if links:
            try:
                webbrowser.open(links[0][1])
            except Exception:
                pass

    def _toggle_help(self) -> None:
        # Placeholder – help is always shown in this minimal TUI
        pass

    def _handle_text_input(self, ch: int) -> None:
        fields = self.steps[self.step_index].get("fields", [])
        if not fields:
            return
        field = fields[self.field_index]
        current = self._get_field_value(field)
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            current = current[:-1]
        elif 32 <= ch <= 126:  # printable ASCII
            current += chr(ch)
        self._set_field_value(field, current)

    def _can_advance(self) -> bool:
        step = self.steps[self.step_index]
        fields = step.get("fields", [])
        for f in fields:
            if f.get("optional"):
                continue
            val = self._get_field_value(f).strip()
            if val == "":
                return False
        return True

    def _save(self) -> None:
        existing = _load_env_file(self.project_root)
        to_write = {k: v for k, v in self.env_values.items() if isinstance(v, str) and v.strip() != "" and existing.get(k) != v}
        self._last_save_result = _write_env(self.project_root, to_write)
        config_obj = {
            "household": {"displayName": "Household"},
            "radarr": self.config_values.get("radarr", {}),
            "sonarr": self.config_values.get("sonarr", {}),
        }
        _write_config(self.project_root, config_obj)
        _write_household_prefs(self.project_root)

    def _draw_done(self, stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        stdscr.clear()
        env_written = False
        env_path: Path | None = None
        suggest_path: Path | None = None
        if hasattr(self, "_last_save_result") and self._last_save_result is not None:
            env_written, env_path, suggest_path = self._last_save_result
        if env_written:
            msg = "Saved .env, config/config.yaml, and data/household_preferences.json\nPress any key to exit."
        elif suggest_path is not None:
            msg = (
                "Saved config/config.yaml and data/household_preferences.json\n"
                f"Existing .env left untouched. Suggestions written to: {suggest_path}\n"
                "Press any key to exit."
            )
        else:
            msg = (
                "Saved config/config.yaml and data/household_preferences.json\n"
                "Existing .env left untouched.\n"
                "Press any key to exit."
            )
        stdscr.addstr(2, 2, msg)
        stdscr.refresh()


