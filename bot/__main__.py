import asyncio
import logging
import os
from .discord_bot import run_bot


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("MOVIEBOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass

