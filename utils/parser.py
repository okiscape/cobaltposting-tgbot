"""
caption_formatter.py - парсинг метаданных из URL и форматирование подписей.

Доступные плейсхолдеры:
    {url}               - оригинальная ссылка
    {service}           - название сервиса с заглавной буквы (YouTube, TikTok, ...)
    {service_lower}     - название сервиса в нижнем регистре (youtube, tiktok, ...)
    {publisher}         - юзернейм/никнейм автора (@username или username)
    {publisher_name}    - без @ (просто username)
    {video_id}          - ID видео/поста (если извлекаемо)
    {post_url}          - канонический URL поста (без query-параметров)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlparse

# ──────────────────────────────────────────────
# Типы
# ──────────────────────────────────────────────


@dataclass
class UrlMeta:
    url: str
    service: str = "Unknown"  # с заглавной
    service_lower: str = "unknown"
    publisher: Optional[str] = None  # с @
    publisher_name: Optional[str] = None  # без @
    video_id: Optional[str] = None
    post_url: Optional[str] = None  # чистый URL без лишних параметров

    def format(self, template: str) -> str:
        """Подставляет плейсхолдеры в шаблон."""
        replacements = {
            "{url}": self.url,
            "{service}": self.service,
            "{service_lower}": self.service_lower,
            "{publisher}": self.publisher,
            "{publisher_name}": self.publisher_name,
            "{video_id}": self.video_id or "",
            "{post_url}": self.post_url or self.url,
        }
        result = template
        for key, val in replacements.items():
            result = result.replace(key, val if val else "")
        return result


# ──────────────────────────────────────────────
# Парсеры по сервисам
# ──────────────────────────────────────────────


def _make(
    url: str,
    service: str,
    publisher: str = None,
    video_id: str = None,
    post_url: str = None,
) -> UrlMeta:
    pub = publisher.lstrip("@") if publisher else None
    return UrlMeta(
        url=url,
        service=service,
        service_lower=service.lower(),
        publisher=f"@{pub}" if pub else None,
        publisher_name=pub,
        video_id=video_id,
        post_url=post_url or url,
    )


def _parse_youtube(url: str, parsed) -> UrlMeta:
    # Форматы:
    #   youtube.com/watch?v=ID
    #   youtube.com/shorts/ID
    #   youtube.com/@channel / youtube.com/c/channel / youtube.com/user/channel
    #   youtu.be/ID
    video_id = None
    publisher = None

    qs = parse_qs(parsed.query)
    path = parsed.path.rstrip("/")

    if parsed.netloc in ("youtu.be",):
        video_id = path.lstrip("/")
    elif "watch" in path:
        video_id = qs.get("v", [None])[0]
    elif "/shorts/" in path:
        video_id = path.split("/shorts/")[-1]
    elif "/embed/" in path:
        video_id = path.split("/embed/")[-1]

    # Канал
    for prefix in ("/@", "/c/", "/user/", "/channel/"):
        if prefix in path:
            publisher = path.split(prefix)[-1].split("/")[0]
            break

    post_url = f"https://youtu.be/{video_id}" if video_id else url
    return _make(url, "youtube", publisher, video_id, post_url)


def _parse_tiktok(url: str, parsed) -> UrlMeta:
    # Форматы:
    #   tiktok.com/@user/video/ID
    #   vm.tiktok.com/SHORTCODE  (короткая - publisher недоступен)
    #   vt.tiktok.com/SHORTCODE
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    m = re.match(r"/@([^/]+)/video/(\d+)", path)
    if m:
        publisher = m.group(1)
        video_id = m.group(2)

    post_url = (
        f"https://www.tiktok.com/@{publisher}/video/{video_id}"
        if publisher and video_id
        else url
    )

    return _make(url, "tiktok", publisher, video_id, post_url)


def _parse_twitter(url: str, parsed) -> UrlMeta:
    # twitter.com/user/status/ID
    # x.com/user/status/ID
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    # NO @ from publisher

    post_url = (
        f"https://x.com/{publisher}/status/{video_id}"
        if publisher and video_id
        else url
    )

    m = re.match(r"/([^/]+)/status/(\d+)", path)
    if m:
        publisher = m.group(1).lstrip("@")
        video_id = m.group(2)

    return _make(url, "x", publisher, video_id, post_url)


def _parse_instagram(url: str, parsed) -> UrlMeta:
    # instagram.com/p/CODE/
    # instagram.com/reel/CODE/
    # instagram.com/user/   (профиль)
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    for prefix in ("/p/", "/reel/", "/tv/"):
        if prefix in path:
            video_id = path.split(prefix)[-1].split("/")[0]
            break

    # Профиль вида /username (без /p/ /reel/ и т.д.)
    parts = [p for p in path.split("/") if p]
    if not video_id and len(parts) == 1:
        publisher = parts[0]

    post_url = f"https://www.instagram.com/p/{video_id}/" if video_id else url
    return _make(url, "Instagram", publisher, video_id, post_url)


def _parse_reddit(url: str, parsed) -> UrlMeta:
    # reddit.com/r/sub/comments/ID/title/
    # reddit.com/u/user
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    m = re.search(r"/r/[^/]+/comments/([a-z0-9]+)", path)
    if m:
        video_id = m.group(1)

    m2 = re.match(r"/u(?:ser)?/([^/]+)", path)
    if m2:
        publisher = m2.group(1)

    post_url = f"https://www.reddit.com{path}" if path else url
    return _make(url, "Reddit", publisher, video_id, post_url)


def _parse_soundcloud(url: str, parsed) -> UrlMeta:
    # soundcloud.com/artist/track
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    publisher = parts[0] if len(parts) >= 1 else None
    video_id = parts[1] if len(parts) >= 2 else None
    return _make(url, "SoundCloud", publisher, video_id, url)


def _parse_bluesky(url: str, parsed) -> UrlMeta:
    # bsky.app/profile/user.bsky.social/post/ID
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    m = re.match(r"/profile/([^/]+)/post/([^/]+)", path)
    if m:
        publisher = m.group(1)
        video_id = m.group(2)

    post_url = (
        f"https://bsky.app/profile/{publisher}/post/{video_id}"
        if publisher and video_id
        else url
    )
    return _make(url, "Bluesky", publisher, video_id, post_url)


def _parse_tumblr(url: str, parsed) -> UrlMeta:
    # user.tumblr.com/post/ID
    # tumblr.com/user/ID
    path = parsed.path.rstrip("/")
    publisher = None
    video_id = None

    host_parts = parsed.netloc.split(".")
    if host_parts[0] not in ("www", "tumblr"):
        publisher = host_parts[0]

    m = re.search(r"/post/(\d+)", path)
    if m:
        video_id = m.group(1)

    if not publisher:
        parts = [p for p in path.split("/") if p]
        if parts:
            publisher = parts[0]

    return _make(url, "Tumblr", publisher, video_id, url)


def _parse_pinterest(url: str, parsed) -> UrlMeta:
    # pinterest.com/user/board/  или  pin.it/CODE
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    publisher = parts[0] if len(parts) >= 1 else None
    video_id = parts[2] if len(parts) >= 3 else None
    return _make(url, "Pinterest", publisher, video_id, url)


# ──────────────────────────────────────────────
# Роутер
# ──────────────────────────────────────────────

_PARSERS = {
    # YouTube
    "youtube.com": _parse_youtube,
    "www.youtube.com": _parse_youtube,
    "youtu.be": _parse_youtube,
    "m.youtube.com": _parse_youtube,
    # TikTok
    "tiktok.com": _parse_tiktok,
    "www.tiktok.com": _parse_tiktok,
    "vm.tiktok.com": _parse_tiktok,
    "vt.tiktok.com": _parse_tiktok,
    # Twitter / X
    "twitter.com": _parse_twitter,
    "www.twitter.com": _parse_twitter,
    "x.com": _parse_twitter,
    "www.x.com": _parse_twitter,
    # Instagram
    "instagram.com": _parse_instagram,
    "www.instagram.com": _parse_instagram,
    # Reddit
    "reddit.com": _parse_reddit,
    "www.reddit.com": _parse_reddit,
    "old.reddit.com": _parse_reddit,
    "redd.it": _parse_reddit,
    # SoundCloud
    "soundcloud.com": _parse_soundcloud,
    "www.soundcloud.com": _parse_soundcloud,
    # Bluesky
    "bsky.app": _parse_bluesky,
    # Tumblr
    "tumblr.com": _parse_tumblr,
    "www.tumblr.com": _parse_tumblr,
    # Pinterest
    "pinterest.com": _parse_pinterest,
    "www.pinterest.com": _parse_pinterest,
    "pin.it": _parse_pinterest,
}


def parse_url(url: str) -> UrlMeta:
    """
    Парсит URL и возвращает UrlMeta со всеми доступными метаданными.

    Использование:
        meta = parse_url("https://www.tiktok.com/@username/video/123456")
        caption = meta.format("📹 {publisher} on {service}\\n{url}")
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        if host in _PARSERS:
            return _PARSERS[host](url, parsed)

        # tumblr subdomain (user.tumblr.com)
        if host.endswith(".tumblr.com"):
            return _parse_tumblr(url, parsed)

        # Неизвестный сервис - вернуть хоть что-то
        print("unknown service " + host)
        service = host.removeprefix("www.").split(".")[0].capitalize()
        return _make(url, service, None, None, url)

    except Exception:
        return UrlMeta(url=url, post_url=url)
