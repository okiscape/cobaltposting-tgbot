import os

import pytz
from aiogram.client.default import DefaultBotProperties
from dotenv import dotenv_values

defaults = DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True)
databasePath = "utils/base.db"

defaultTimezone = pytz.timezone("Europe/Moscow")

env = {**dotenv_values(), **os.environ}

adminsIds = env["ADMINS_IDS"].split(",")

logIgnoreTypes = ["preload"]

nodes = env["COBALT_NODES"].split(",")


class tokens:
    token = env["TELEGRAM_BOT_TOKEN"]
