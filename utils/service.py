import asyncio
import datetime
import importlib
import sys

import aiohttp
import aiosqlite
from aiogram import Bot as aiBot
from aiogram import Dispatcher

from utils import bot_logging, cobaltAPI, config, databaseMethods, shortcuts


class Bot(aiBot):
    """Custom Bot Class"""

    def __init__(self):
        """Custom Bot Class"""
        self.config = config
        self.dispatcher = Dispatcher()
        self.admins = config.adminsIds
        self.db: aiosqlite.Connection = ...
        self.dbm: databaseMethods.DatabaseMethods = ...
        self.sh = shortcuts
        self.logging = bot_logging.Logging()
        self.log = self.logging.info
        self.logIgnoreTypes = config.logIgnoreTypes
        self.handlers_list = []  # список модулей, например ['handlers.start']
        self.startedAt = self.sh.nowdt()
        self.cobalt = cobaltAPI.CobaltMethods(self.logging, config.nodes)
        self.cobalt._session = ...
        self.cobalt._owned = False

        super().__init__(
            token=config.botToken,
            default=config.defaults,
            #  session=AiohttpSession(proxy="socks5://127.0.0.1:3067")
        )

    async def databaseConnect(self):
        self.db = await aiosqlite.connect(self.config.databasePath)
        self.dbm: databaseMethods.DatabaseMethods = databaseMethods.DatabaseMethods(
            self
        )
        await self.dbm.createTable(
            "users",
            {
                "userId": "INTEGER NOT NULL PRIMARY KEY",
                "channelId": "INTEGER NOT NULL",
                "stats": "TEXT",
                "createdAt": "INTEGER NOT NULL",
                "format": "TEXT",
            },
        )
        return self.db

    def load_cog(self, module_name: str):
        if module_name in sys.modules:
            del sys.modules[module_name]
        module = importlib.import_module(module_name)
        if hasattr(module, "setup"):
            module.setup(self)

    def load_handlers(self, handlers: list[str]):
        self.handlers_list = handlers
        for module_name in handlers:
            try:
                self.load_cog(module_name)
                self.logging.info(f"Module {module_name} loaded", type="modules")
            except Exception as e:
                self.logging.info(
                    f"Error loading {module_name}: {str(e)}", type="error"
                )
                raise e

    def run(self):
        try:

            async def a():
                self.cobalt._session = aiohttp.ClientSession()
                await self.databaseConnect()
                me = await self.me()
                self.logging.info(
                    f"Logged in as {me.full_name}",
                    f"Username: https://t.me/{me.username}",
                    f"Bot ID: {me.id}",
                    type="global",
                )

                try:
                    # await self.delete_webhook(drop_pending_updates=True)
                    await self.dispatcher.start_polling(self)
                except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
                    self.logging.info("Stop signal recieved", type="internal")
                finally:
                    await self.session.close()
                    await self.cobalt._session.close()
                    self.logging.info("Bot session closed", type="internal")
                    await self.db.close()
                    self.logging.info("Database connection closed", type="internal")

            # self.log("Bot start...", type="internal")

            asyncio.run(a())

        finally:
            self.logging.info("Nothing further remaining to do!", type="global")

    @property
    def datetime(self):
        return datetime.datetime
