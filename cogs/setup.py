from aiogram.fsm.state import State, StatesGroup
from aiogram.types import MessageOriginChannel

import cog


class SetupStates(StatesGroup):
    waiting_for_channel = State()


class Handler(cog.Cog):
    def __init__(self, bot: cog.Bot):
        super().__init__(bot)

    @cog.regMessage(cog.F.text == "/setup")
    async def command(self, message: cog.Message, state: cog.FSMContext):
        await state.set_state(SetupStates.waiting_for_channel)
        await message.answer(
            "Forward any message from your channel to link it.\n"
            "Make sure I'm already added there as an administrator."
        )

    @cog.regMessage(
        SetupStates.waiting_for_channel and cog.F.forward_origin.type == "channel"
    )
    async def handle_forwarded(self, message: cog.Message, state: cog.FSMContext):
        origin: MessageOriginChannel = message.forward_origin
        chat = origin.chat

        if chat.type != "channel":
            await message.answer("That doesn't seem to be a channel, try again.")
            return

        try:
            member = await self.bot.get_chat_member(chat.id, message.from_user.id)
            if not member:
                await message.answer("You're not in that channel, try again.")
                return

            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            if bot_member.status != "administrator":
                await message.answer(
                    "⚠️ I'm in that channel but I'm not an administrator.\n"
                    "Please give me admin rights and try again."
                )
                return

        except Exception as e:
            await message.answer(
                "⚠️ I don't seem to be in that channel.\n"
                "Add me as an administrator first, then forward a message from it. (unexpected error)"
            )
            raise e

        try:
            user_member = await self.bot.get_chat_member(chat.id, message.from_user.id)
            if user_member.status not in ("administrator", "creator"):
                await message.answer(
                    "⚠️ You are not an administrator of that channel.\n"
                    "Only channel admins can link it for posting."
                )
                return
        except Exception:
            await message.answer("⚠️ Could not verify your role in that channel.")
            return

        user = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if not user:
            await self.bot.dbm.createUser(
                userId=message.from_user.id,
                createdAt=cog.sh.nowdtts(),
                channelId=chat.id,
            )
        else:
            await self.bot.dbm.updateUser(
                userId=message.from_user.id,
                channelId=chat.id,
            )

        await self.bot.dbm.readUsers(userId=message.from_user.id, cacheOverwrite=True)
        await state.clear()

        display = f"<b>{chat.title}</b>"
        if chat.username:
            display += f" (@{chat.username})"
        await message.answer(
            f"✅ Successfully linked to channel {display}!",
            parse_mode="HTML",
        )

    @cog.regMessage(SetupStates.waiting_for_channel)
    async def handle_wrong_input(self, message: cog.Message, state: cog.FSMContext):
        await message.answer(
            "Please forward a message from your channel.\n"
            "Other input is not accepted during setup."
        )


def setup(bot: cog.Bot):
    Handler(bot=bot).register()
