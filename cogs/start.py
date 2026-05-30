import cog


class Handler(cog.Cog):
    def __init__(self, bot: cog.Bot):
        super().__init__(bot)

    @cog.regMessage(cog.F.text == "/start")
    async def command(self, message: cog.Message):
        user = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if user:
            user = user[0]
            channel = await self.bot.get_chat(user.channelId)
            await message.answer(f"""<b>Welcome to the Cobalt Posting bot!</b>
You can use this bot for quick and customizable posting in your channel.

Or /setup to change your channel.
You're currently posting in <b><a href="{channel.invite_link}">{channel.title}</a></b>""")
        else:
            await message.answer("""<b>Welcome to the Cobalt Posting bot!</b>
You can use this bot for quick and customizable posting in your channel.

Or /setup to setup bot in your channel.""")

    @cog.regMessage(cog.F.text == "/about")
    async def aboutCommand(self, message: cog.Message):
        await message.answer(
            """This is the Cobalt-powered Posting bot, a quick and customizable posting bot for your channel.
<i>This bot is still in development, so please, be patient with any issues.</i>

<b>This bot uses:</b>
 - https://github.com/imputnet/cobalt
 - https://github.com/aiogram/aiogram
and maybe something else

[Source](https://github.com/okiscape/cobaltposting-tgbot)<i> created by <a href="https://github.com/okiscape">okiscape</a> (@nvr_bio)</i>"""
        )


def setup(bot: cog.Bot):
    Handler(bot=bot).register()
