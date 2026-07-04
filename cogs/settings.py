import json

import cog


class Handler(cog.Cog):
    def __init__(self, bot: cog.Bot):
        super().__init__(bot)

    @cog.regMessage(cog.F.text == "/settings")
    async def settings(self, message: cog.Message):
        users = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if not users:
            return await message.answer(
                "You don't have a channel set up yet. Use /setup first."
            )

        user = users[0]

        nodes = user.customNodes or []
        replace = user.replaceNodes

        if not nodes:
            nodes_display = "Not set (using bot's default nodes)"
        else:
            nodes_display = "\n".join(f"• {n}" for n in nodes)

        mode_display = "Replace bot nodes" if replace else "Add to bot nodes"

        await message.answer(
            f"""<b>Your settings</b>

<b>Custom nodes:</b>
{nodes_display}

<b>Mode:</b> {mode_display}

<i>Commands:</i>
<code>/settings nodes url1,url2,...</code> - set custom nodes
<code>/settings nodes</code> - clear custom nodes
<code>/settings mode</code> - toggle replace/add mode""",
            parse_mode="HTML",
        )

    @cog.regMessage(cog.F.text.startswith("/settings nodes"))
    async def set_nodes(self, message: cog.Message):
        users = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if not users:
            return await message.answer(
                "You don't have a channel set up yet. Use /setup first."
            )

        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            return

        raw = parts[2] if len(parts) > 2 else ""

        if not raw.strip():
            await self.bot.dbm.updateUser(
                userId=message.from_user.id,
                customNodes=json.dumps([]),
            )
            await self.bot.dbm.readUsers(
                userId=message.from_user.id, cacheOverwrite=True
            )
            return await message.answer(
                "Custom nodes cleared. Bot will use default nodes."
            )
        else:
            nodes = [n.strip() for n in raw.split(",") if n.strip()]
            if not nodes:
                return await message.answer(
                    "No valid nodes provided. Use comma-separated URLs."
                )

            await self.bot.dbm.updateUser(
                userId=message.from_user.id,
                customNodes=json.dumps(nodes),
            )
            await self.bot.dbm.readUsers(
                userId=message.from_user.id, cacheOverwrite=True
            )
            await message.answer(
                f"Custom nodes set ({len(nodes)}):\n"
                + "\n".join(f"• {n}" for n in nodes)
            )

    @cog.regMessage(cog.F.text == "/settings mode")
    async def toggle_mode(self, message: cog.Message):
        users = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if not users:
            return await message.answer(
                "You don't have a channel set up yet. Use /setup first."
            )

        user = users[0]
        new_mode = not user.replaceNodes

        await self.bot.dbm.updateUser(
            userId=message.from_user.id,
            replaceNodes=int(new_mode),
        )
        await self.bot.dbm.readUsers(userId=message.from_user.id, cacheOverwrite=True)

        mode_text = (
            "Replace bot nodes with my custom nodes"
            if new_mode
            else "Add my custom nodes to bot nodes"
        )
        await message.answer(f"Mode changed to: <b>{mode_text}</b>", parse_mode="HTML")

    @cog.regMessage(cog.F.text.startswith("/settings"))
    async def zzz_settings_fallback(self, message: cog.Message):
        await message.answer(
            "Unknown settings command.\n\n"
            "<code>/settings</code> - show current settings\n"
            "<code>/settings nodes url1,url2,...</code> - set custom nodes\n"
            "<code>/settings nodes</code> - clear custom nodes\n"
            "<code>/settings mode</code> - toggle replace/add mode",
            parse_mode="HTML",
        )


def setup(bot: cog.Bot):
    Handler(bot=bot).register()
