import pytz
from aiogram.client.default import DefaultBotProperties
from dotenv import dotenv_values

defaults = DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True)
databasePath = "utils/base.db"

defaultTimezone = pytz.timezone("Europe/Moscow")

logIgnoreTypes = ["preload"]

env = dotenv_values()

adminsIds = env.get("ADMINS_IDS", "").split(",")
nodes = env.get("COBALT_NODES", "").split(",")
botToken = env.get("TELEGRAM_BOT_TOKEN", "")
errorsReportChatId = env.get("ERRORS_REPORT_CHATID", "")

if None in (adminsIds, nodes, botToken, errorsReportChatId):
    raise ValueError(
        "Missing required environment variables("
        + ", ".join(
            [
                var.__repr__()
                for var in (adminsIds, nodes, botToken, errorsReportChatId)
                if var is None
            ]
        )
        + ")"
    )
