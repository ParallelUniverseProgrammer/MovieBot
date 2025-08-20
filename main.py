import os
import sys
from pathlib import Path
import logging

from config.loader import load_settings, load_runtime_config, is_config_complete


def main() -> None:
    project_root = Path(__file__).parent
    # Basic logging config
    logging.basicConfig(
        level=os.getenv("MOVIEBOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings(project_root)
    runtime_config = load_runtime_config(project_root)

    if not is_config_complete(settings, runtime_config):
        print("Configuration incomplete. Launching setup wizard...\n")
        from scripts.setup_wizard import run_interactive

        run_interactive(project_root)
        print("\nSetup complete. Re-run `python main.py` to start the bot or run `python -m bot.discord_bot`.")
        return

    print("Configuration looks good.")
    print("- Discord bot not auto-started in scaffold. To start: `python -m bot.discord_bot`\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)

