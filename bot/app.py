"""Bot application bootstrap and dispatcher builder."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web

from config import (
    AppSettings,
    BotRuntimeConfig,
    load_server_registry,
    load_settings,
    resolve_config_path,
)

logger = logging.getLogger(__name__)


def create_bot(token: str) -> Bot:
    """Create Bot instance with default properties."""
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def build_dispatcher(settings: AppSettings, config: BotRuntimeConfig | None = None) -> Dispatcher:
    """Build and configure the dispatchers with all routers."""
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    from handlers import common, echo, navigation, status, webhook

    dp.include_router(webhook.router)
    dp.include_router(common.router)
    dp.include_router(status.router)
    dp.include_router(echo.router)
    dp.include_router(navigation.router)

    return dp


def build_app() -> tuple[Bot, Dispatcher, AppSettings]:
    """Build complete app with bot, dispatcher, and settings."""
    settings, config_path = load_settings()
    resolved_path = resolve_config_path(config_path)
    load_server_registry(resolved_path)

    runtime_config = BotRuntimeConfig()
    dp = build_dispatcher(settings, runtime_config)
    bot = create_bot(settings.bot_token)

    return bot, dp, settings


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start bot in polling mode."""
    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot)


async def start_webhook(bot: Bot, dp: Dispatcher, settings: AppSettings) -> None:
    """Start bot in webhook mode with aiohttp server."""
    config_path = resolve_config_path(settings.config_path)
    _ = load_server_registry(config_path)

    runtime_cfg = load_settings()[0]
    webhook_cfg = runtime_cfg.webhook

    app = web.Application()
    setup_application(app, dp, webhook_path=webhook_cfg.path)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, webhook_cfg.base_url, 8080)
    await site.start()

    logger.info(f"Webhook listener started on {webhook_cfg.base_url}")


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

    async def run_webhook(self) -> None:
        """Run bot in webhook mode."""
        if not self.bot or not self.dp or not self.settings:
            self.initialize()
        assert self.bot and self.dp and self.settings
        await start_webhook(self.bot, self.dp, self.settings)


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
