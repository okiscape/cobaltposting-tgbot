print("-" * 25)

import cog

bot = cog.Bot()
bot.logging.info("Bot initalized", type="preload")

bot.load_handlers(
    handlers=[
        "cogs.middlewares",
        "cogs.start",
        "cogs.setup",
        "cogs.settings",
        "cogs.download",
    ]
)
bot.logging.info("All modules loaded", type="preload")

bot.logging.info("Logging in...", type="global")

bot.run()
