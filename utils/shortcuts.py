from datetime import datetime

from utils import config


def nowdtts():
    """**Now**<b>D</b>ate**T**ime**T**ime**S**tamp"""
    return round(datetime.now(config.defaultTimezone).timestamp())


def nowdt():
    return datetime.now(config.defaultTimezone)


def datetime_from_timestamp(timestamp: int | float):
    return datetime.fromtimestamp(timestamp, config.defaultTimezone)


def escapeHtml(text):
    return str(text).replace("<", "&lt;").replace(">", "&gt;")
