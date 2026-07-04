import re
from typing import Literal

import cog


def _media_kind(content_type: str) -> Literal["photo", "video", "gif", "document"]:
    if content_type.startswith("video"):
        return "video"
    if content_type == "image/gif":
        return "gif"
    if content_type.startswith("image"):
        return "photo"
    return "document"


class Handler(cog.Cog):
    def __init__(self, bot: cog.Bot):
        super().__init__(bot)
        self.rateLimitCache = cog.types.AsyncLRUTTLCache(maxsize=100, ttl=4)
        self._downloading: set[int] = set()

    @cog.regMessage(cog.F.text)
    async def downloadTrigger(self, message: cog.Message):
        users = await self.bot.dbm.readUsers(userId=message.from_user.id)
        if not users:
            return await message.reply(
                cog.sh.escapeHtml(
                    "Seems like you doesn't have a channel setted up for posting :<\n"
                    "You can use /setup to set up a channel for posting.\n"
                    "For direct downloads you can use @coboldbot."
                )
            )
        user = users[0]

        try:
            bot_member = await self.bot.get_chat_member(user.channelId, self.bot.id)
            if bot_member.status != "administrator":
                return await message.reply(
                    "⚠️ I'm no longer an administrator in your linked channel.\n"
                    "Please add me as admin and try again."
                )
        except Exception:
            return await message.reply(
                "⚠️ Could not access your linked channel.\n"
                "I might have been removed. Use /setup to link a new channel."
            )

        try:
            user_member = await self.bot.get_chat_member(
                user.channelId, message.from_user.id
            )
            if user_member.status not in ("administrator", "creator"):
                return await message.reply(
                    "⚠️ You are no longer an administrator of the linked channel.\n"
                    "Posting is disabled. Contact the channel owner to restore your rights."
                )
        except Exception:
            return await message.reply(
                "⚠️ Could not verify your role in the linked channel."
            )

        if not re.match(r"(http|https):\/\/", message.text):
            return await message.reply(
                "It doesnt seem like a link, i don't know how to download it."
            )

        user_id = message.from_user.id

        if user_id in self._downloading:
            return await message.reply(
                "Already downloading your previous request, please wait."
            )

        rate_ts = await self.rateLimitCache.get(user_id)
        if rate_ts is not None:
            seconds_left = 4 - (cog.sh.nowdtts() - rate_ts)
            return await message.reply(
                f"You're being rate limited, try again in {max(1, seconds_left):.0f}s."
            )

        self._downloading.add(user_id)
        rmsg = await message.answer("Downloading...")

        try:
            self.bot.log(f"Starting download for URL: {message.text}", type="debug")
            downloaded = await self.bot.cobalt.download_all_picker(url=message.text)
            self.bot.log(
                f"Downloaded {len(downloaded)} file(s): "
                + ", ".join(f.filename for f in downloaded),
                type="debug",
            )

            meta = cog.parser.parse_url(message.text)
            if meta.publisher:
                caption = meta.format(
                    '<a href="{post_url}">&gt; {service_lower}/{publisher}</a>'
                )
            else:
                caption = meta.format('<a href="{post_url}">&gt; {service_lower}</a>')

            sentmsg = None
            media_group: list = []
            first_sent = True

            async def _flush_group():
                nonlocal sentmsg, first_sent
                if not media_group:
                    return
                self.bot.log(
                    f"Flushing media group of {len(media_group)} item(s)", type="debug"
                )
                if first_sent:
                    first_item = media_group[0]
                    if isinstance(first_item, cog.aiotypes.InputMediaPhoto):
                        media_group[0] = cog.aiotypes.InputMediaPhoto(
                            media=first_item.media,
                            caption=caption,
                            parse_mode="HTML",
                        )
                    elif isinstance(first_item, cog.aiotypes.InputMediaVideo):
                        media_group[0] = cog.aiotypes.InputMediaVideo(
                            media=first_item.media,
                            caption=caption,
                            parse_mode="HTML",
                        )
                    first_sent = False
                sentmsg = await self.bot.send_media_group(
                    chat_id=user.channelId,
                    media=list(media_group),
                )
                media_group.clear()

            async def _send_single(f, kind: str):
                nonlocal sentmsg, first_sent
                self.bot.log(
                    f"Sending single file: {f.filename} as {kind}", type="debug"
                )
                cap = caption if first_sent else None
                pm = "HTML" if first_sent else None
                first_sent = False
                buf = cog.aiotypes.BufferedInputFile(f.read(), filename=f.filename)
                if kind == "gif":
                    sentmsg = [
                        await self.bot.send_animation(
                            chat_id=user.channelId,
                            animation=buf,
                            caption=cap,
                            parse_mode=pm,
                        )
                    ]
                elif kind == "video":
                    sentmsg = [
                        await self.bot.send_video(
                            chat_id=user.channelId,
                            video=buf,
                            caption=cap,
                            parse_mode=pm,
                        )
                    ]
                else:
                    sentmsg = [
                        await self.bot.send_document(
                            chat_id=user.channelId,
                            document=buf,
                            caption=cap,
                            parse_mode=pm,
                        )
                    ]

            for f in downloaded:
                kind = _media_kind(f.content_type)
                self.bot.log(
                    f"Processing file: {f.filename} | content_type={f.content_type} | kind={kind}",
                    type="debug",
                )
                buf = cog.aiotypes.BufferedInputFile(f.read(), filename=f.filename)

                if kind in ("photo", "video"):
                    if kind == "photo":
                        media_group.append(cog.aiotypes.InputMediaPhoto(media=buf))
                    else:
                        media_group.append(cog.aiotypes.InputMediaVideo(media=buf))

                    if len(media_group) == 10:
                        await _flush_group()

                else:
                    await _flush_group()
                    await _send_single(f, kind)

            await _flush_group()

            self.bot.log("All files sent successfully", type="debug")

            channel = await self.bot.get_chat(user.channelId)
            await rmsg.edit_text(
                f"Sent to <b>{channel.title}</b>!",
                parse_mode="HTML",
                reply_markup=cog.aiotypes.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            cog.aiotypes.InlineKeyboardButton(
                                text="View in channel", url=sentmsg[0].get_url()
                            )
                        ]
                    ]
                ),
            )

            await self.rateLimitCache.set(user_id, cog.sh.nowdtts())

        except Exception as e:
            if isinstance(e, cog.cobaltAPI.CobaltAllNodesFailed):
                await rmsg.edit_text(
                    "Currently i can't download this content from this service, try again later."
                )
                raise e

            await rmsg.edit_text(
                "An error occurred, already reported to admins. Try again later."
            )
            raise e

        finally:
            self._downloading.discard(user_id)


def setup(bot: cog.Bot):
    Handler(bot=bot).register()
