"""Bot application bootstrap and dispatcher builder."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import AppSettings, load_server_registry, load_settings
from db import init_database

logger = logging.getLogger(__name__)


def create_bot(token: str) -> Bot:
    """Create Bot instance with default properties."""
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def build_dispatcher(settings: AppSettings) -> Dispatcher:
    """Build and configure the dispatchers with all routers."""
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    from handlers import common, echo, navigation, status

    dp.include_router(common.router)
    dp.include_router(status.router)
    dp.include_router(echo.router)
    dp.include_router(navigation.router)

    return dp


def build_app() -> tuple[Bot, Dispatcher, AppSettings]:
    """Build complete app with bot, dispatcher, and settings."""
    settings, config_path = load_settings()
    if not config_path.is_file():
        msg = f"Server configuration file not found: {config_path}"
        raise FileNotFoundError(msg)

    load_server_registry(config_path)
    init_database(settings.database_path)

    dp = build_dispatcher(settings)
    bot = create_bot(settings.bot_token)

    return bot, dp, settings


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start bot in polling mode."""
    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot)


class BotApp:
    """Container for running the bot."""

    def __init__(self) -> None:
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self.settings: AppSettings | None = None

    def initialize(self) -> None:
        """Initialize bot components."""
        self.bot, self.dp, self.settings = build_app()

    async def run_polling(self) -> None:
        """Run bot in polling mode."""
        if not self.bot or not self.dp:
            self.initialize()
        assert self.bot and self.dp
        await start_polling(self.bot, self.dp)


def main() -> None:
    """Entry point for the bot."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    app = BotApp()

    try:
        asyncio.run(app.run_polling())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        if app.bot:
            asyncio.run(app.bot.session.close())


if __name__ == "__main__":
    main()
