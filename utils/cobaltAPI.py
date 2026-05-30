"""
cobalt.py — Async клиент для cobalt API (v10+)
https://github.com/imputnet/cobalt/blob/main/docs/api.md
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

import aiohttp

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class AudioBitrate(str, Enum):
    B320 = "320"
    B256 = "256"
    B128 = "128"
    B96 = "96"
    B64 = "64"
    B8 = "8"


class AudioFormat(str, Enum):
    BEST = "best"
    MP3 = "mp3"
    OGG = "ogg"
    WAV = "wav"
    OPUS = "opus"


class DownloadMode(str, Enum):
    AUTO = "auto"
    AUDIO = "audio"
    MUTE = "mute"


class FilenameStyle(str, Enum):
    CLASSIC = "classic"
    PRETTY = "pretty"
    BASIC = "basic"
    NERDY = "nerdy"


class VideoQuality(str, Enum):
    MAX = "max"
    Q4320 = "4320"
    Q2160 = "2160"
    Q1440 = "1440"
    Q1080 = "1080"
    Q720 = "720"
    Q480 = "480"
    Q360 = "360"
    Q240 = "240"
    Q144 = "144"


class YoutubeVideoCodec(str, Enum):
    H264 = "h264"
    AV1 = "av1"
    VP9 = "vp9"


class YoutubeVideoContainer(str, Enum):
    AUTO = "auto"
    MP4 = "mp4"
    WEBM = "webm"
    MKV = "mkv"


class LocalProcessing(str, Enum):
    DISABLED = "disabled"
    PREFERRED = "preferred"
    FORCED = "forced"


class ResponseStatus(str, Enum):
    TUNNEL = "tunnel"
    REDIRECT = "redirect"
    LOCAL_PROCESSING = "local-processing"
    PICKER = "picker"
    ERROR = "error"


class PickerItemType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    GIF = "gif"


# ──────────────────────────────────────────────
# Request / Response types
# ──────────────────────────────────────────────


@dataclass
class CobaltRequest:
    """Тело запроса к POST /"""

    url: str

    # General
    audioBitrate: AudioBitrate = AudioBitrate.B128
    audioFormat: AudioFormat = AudioFormat.MP3
    downloadMode: DownloadMode = DownloadMode.AUTO
    filenameStyle: FilenameStyle = FilenameStyle.BASIC
    videoQuality: VideoQuality = VideoQuality.Q1080
    disableMetadata: bool = False
    alwaysProxy: bool = False
    localProcessing: LocalProcessing = LocalProcessing.DISABLED
    subtitleLang: Optional[str] = None

    # YouTube
    youtubeVideoCodec: YoutubeVideoCodec = YoutubeVideoCodec.H264
    youtubeVideoContainer: YoutubeVideoContainer = YoutubeVideoContainer.AUTO
    youtubeDubLang: Optional[str] = None
    youtubeBetterAudio: bool = False
    youtubeHLS: bool = False

    # Service-specific
    convertGif: bool = True
    allowH265: bool = False
    tiktokFullAudio: bool = False

    def to_dict(self) -> dict:
        d: dict = {"url": self.url}

        def _add(key, val, default):
            if val != default:
                d[key] = val.value if isinstance(val, Enum) else val

        _add("audioBitrate", self.audioBitrate, AudioBitrate.B128)
        _add("audioFormat", self.audioFormat, AudioFormat.MP3)
        _add("downloadMode", self.downloadMode, DownloadMode.AUTO)
        _add("filenameStyle", self.filenameStyle, FilenameStyle.BASIC)
        _add("videoQuality", self.videoQuality, VideoQuality.Q1080)
        _add("localProcessing", self.localProcessing, LocalProcessing.DISABLED)
        _add("youtubeVideoCodec", self.youtubeVideoCodec, YoutubeVideoCodec.H264)
        _add(
            "youtubeVideoContainer",
            self.youtubeVideoContainer,
            YoutubeVideoContainer.AUTO,
        )

        if self.disableMetadata:
            d["disableMetadata"] = True
        if self.alwaysProxy:
            d["alwaysProxy"] = True
        if self.youtubeBetterAudio:
            d["youtubeBetterAudio"] = True
        if self.youtubeHLS:
            d["youtubeHLS"] = True
        if not self.convertGif:
            d["convertGif"] = False
        if self.allowH265:
            d["allowH265"] = True
        if self.tiktokFullAudio:
            d["tiktokFullAudio"] = True
        if self.subtitleLang:
            d["subtitleLang"] = self.subtitleLang
        if self.youtubeDubLang:
            d["youtubeDubLang"] = self.youtubeDubLang

        return d


@dataclass
class OutputMetadata:
    album: Optional[str] = None
    composer: Optional[str] = None
    genre: Optional[str] = None
    copyright: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    track: Optional[str] = None
    date: Optional[str] = None
    sublanguage: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "OutputMetadata":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


@dataclass
class OutputObject:
    type: str
    filename: str
    subtitles: bool = False
    metadata: Optional[OutputMetadata] = None

    @classmethod
    def from_dict(cls, data: dict) -> "OutputObject":
        meta_raw = data.get("metadata")
        return cls(
            type=data["type"],
            filename=data["filename"],
            subtitles=data.get("subtitles", False),
            metadata=OutputMetadata.from_dict(meta_raw) if meta_raw else None,
        )


@dataclass
class AudioObject:
    copy: bool
    format: str
    bitrate: str
    cover: bool = False
    cropCover: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "AudioObject":
        return cls(
            copy=data["copy"],
            format=data["format"],
            bitrate=data["bitrate"],
            cover=data.get("cover", False),
            cropCover=data.get("cropCover", False),
        )


@dataclass
class PickerItem:
    type: PickerItemType
    url: str
    thumb: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "PickerItem":
        return cls(
            type=PickerItemType(data["type"]),
            url=data["url"],
            thumb=data.get("thumb"),
        )


@dataclass
class ErrorContext:
    service: Optional[str] = None
    limit: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ErrorContext":
        return cls(service=data.get("service"), limit=data.get("limit"))


@dataclass
class CobaltError:
    code: str
    context: Optional[ErrorContext] = None

    @classmethod
    def from_dict(cls, data: dict) -> "CobaltError":
        ctx_raw = data.get("context")
        return cls(
            code=data["code"],
            context=ErrorContext.from_dict(ctx_raw) if ctx_raw else None,
        )


@dataclass
class TunnelResponse:
    status: ResponseStatus
    url: str
    filename: str


@dataclass
class LocalProcessingResponse:
    status: ResponseStatus
    type: str
    service: str
    tunnel: list[str]
    output: OutputObject
    audio: Optional[AudioObject] = None
    isHLS: bool = False


@dataclass
class PickerResponse:
    status: ResponseStatus
    picker: list[PickerItem]
    audio: Optional[str] = None
    audioFilename: Optional[str] = None


@dataclass
class ErrorResponse:
    status: ResponseStatus
    error: CobaltError


@dataclass
class InstanceInfo:
    version: str
    url: str
    startTime: str
    services: list[str]
    turnstileSitekey: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "InstanceInfo":
        cobalt = data["cobalt"]
        return cls(
            version=cobalt["version"],
            url=cobalt["url"],
            startTime=cobalt["startTime"],
            services=cobalt.get("services", []),
            turnstileSitekey=cobalt.get("turnstileSitekey"),
        )


@dataclass
class SessionResponse:
    token: str
    exp: int


# Тип-объединение для результата запроса
CobaltResponse = (
    TunnelResponse | LocalProcessingResponse | PickerResponse | ErrorResponse
)


# ──────────────────────────────────────────────
# IO-обёртка для скачанного файла
# ──────────────────────────────────────────────


@dataclass
class DownloadedFile:
    """Скачанный файл, хранящийся в памяти."""

    filename: str
    content_type: str
    data: io.BytesIO
    content_length: Optional[int] = None
    estimated_length: Optional[int] = None

    def read(self) -> bytes:
        self.data.seek(0)
        return self.data.read()

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.read())

    def __repr__(self) -> str:
        size = self.content_length or self.estimated_length
        size_str = f"{size} bytes" if size else "unknown size"
        return f"<DownloadedFile filename={self.filename!r} size={size_str}>"


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────


class CobaltApiError(Exception):
    def __init__(self, error: CobaltError):
        self.error = error
        super().__init__(f"[{error.code}] {error.context}")


class CobaltHttpError(Exception):
    def __init__(self, status: int, message: str = ""):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class CobaltAllNodesFailed(Exception):
    """Все ноды вернули ошибку для данного запроса."""

    def __init__(self, errors: dict[str, Exception]):
        self.errors = errors  # {base_url: exception}
        summary = "; ".join(f"{url}: {e}" for url, e in errors.items())
        super().__init__(f"All nodes failed: {summary}")


# ──────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────

# Маппинг хостов на имя сервиса (совпадает с тем что возвращает cobalt)
_HOST_TO_SERVICE: dict[str, str] = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "youtu.be": "youtube",
    "m.youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "www.tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "vt.tiktok.com": "tiktok",
    "twitter.com": "twitter",
    "www.twitter.com": "twitter",
    "x.com": "twitter",
    "www.x.com": "twitter",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "reddit.com": "reddit",
    "www.reddit.com": "reddit",
    "old.reddit.com": "reddit",
    "redd.it": "reddit",
    "twitch.tv": "twitch clips",
    "www.twitch.tv": "twitch clips",
    "clips.twitch.tv": "twitch clips",
    "vimeo.com": "vimeo",
    "www.vimeo.com": "vimeo",
    "soundcloud.com": "soundcloud",
    "www.soundcloud.com": "soundcloud",
    "facebook.com": "facebook",
    "www.facebook.com": "facebook",
    "fb.watch": "facebook",
    "bsky.app": "bluesky",
    "vk.com": "vk",
    "www.vk.com": "vk",
    "dailymotion.com": "dailymotion",
    "www.dailymotion.com": "dailymotion",
    "snapchat.com": "snapchat",
    "www.snapchat.com": "snapchat",
    "tumblr.com": "tumblr",
    "www.tumblr.com": "tumblr",
    "pinterest.com": "pinterest",
    "www.pinterest.com": "pinterest",
    "pin.it": "pinterest",
    "bilibili.com": "bilibili",
    "www.bilibili.com": "bilibili",
    "b23.tv": "bilibili",
    "loom.com": "loom",
    "www.loom.com": "loom",
    "ok.ru": "ok",
    "www.ok.ru": "ok",
    "newgrounds.com": "newgrounds",
    "www.newgrounds.com": "newgrounds",
    "rutube.ru": "rutube",
    "www.rutube.ru": "rutube",
    "streamable.com": "streamable",
    "www.streamable.com": "streamable",
}

# Коды ошибок cobalt, при которых смена ноды может помочь
_RETRYABLE_ERROR_CODES = {
    "error.api.fetch.fail",
    "error.api.unreachable",
    "error.api.network",
    "error.api.timed_out",
    "error.api.fetch.empty",
}


def _service_from_url(url: str) -> Optional[str]:
    """Определяет имя сервиса из URL."""
    try:
        host = urlparse(url).netloc.lower()
        if host in _HOST_TO_SERVICE:
            return _HOST_TO_SERVICE[host]
        if host.endswith(".tumblr.com"):
            return "tumblr"
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────
# Главный класс
# ──────────────────────────────────────────────


class CobaltMethods:
    """
    Async-клиент для cobalt API с поддержкой нескольких нод и памятью
    о последней успешной ноде для каждого сервиса.

    Логика выбора ноды:
        1. Если для сервиса есть запомненная нода — пробуем её первой.
        2. Если она не сработала — перебираем остальные по порядку.
        3. При успехе запоминаем ноду как предпочтительную для этого сервиса.
        4. Если все ноды вернули ошибку — бросаем CobaltAllNodesFailed.
    """

    def __init__(
        self,
        logging,
        base_urls: list[str],
        *,
        api_key: Optional[str] = None,
        bearer: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.logging = logging
        self.base_urls = [url.rstrip("/") for url in base_urls]
        self.api_key = api_key
        self.bearer = bearer
        self._session = session
        self._owned = session is None

        # { service_name: base_url } — последняя успешная нода для сервиса
        self._preferred_node: dict[str, str] = {}
        self.logging.info(
            "CobaltMethods initialized with nodes", self.base_urls, type="cobalt"
        )

    # ── context manager ──────────────────────

    async def __aenter__(self) -> "CobaltMethods":
        if self._owned:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *_) -> None:
        if self._owned and self._session:
            await self._session.close()
            self._session = None

    # ── helpers ──────────────────────────────

    def _node_order(self, service: Optional[str]) -> list[str]:
        """Список нод: предпочтительная для сервиса — первой."""
        preferred = self._preferred_node.get(service) if service else None
        if preferred and preferred in self.base_urls:
            return [preferred] + [u for u in self.base_urls if u != preferred]
        return list(self.base_urls)

    def _remember_node(self, service: Optional[str], base_url: str) -> None:
        if service:
            self._preferred_node[service] = base_url
            self.logging.info(
                f"[cobalt] preferred node for '{service}' set to {base_url}",
                type="cobalt",
            )

    async def _expand_url(self, url: str) -> str:
        """Разворачивает короткие ссылки (vt.tiktok.com и т.д.)"""
        async with self._session.head(
            url,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            return str(resp.url)

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            h["Authorization"] = f"Api-Key {self.api_key}"
        elif self.bearer:
            h["Authorization"] = f"Bearer {self.bearer}"
        if extra:
            h.update(extra)
        return h

    def _parse_response(self, data: dict) -> CobaltResponse:
        status = ResponseStatus(data["status"])

        if status == ResponseStatus.ERROR:
            return ErrorResponse(
                status=status,
                error=CobaltError.from_dict(data["error"]),
            )
        if status in (ResponseStatus.TUNNEL, ResponseStatus.REDIRECT):
            return TunnelResponse(
                status=status,
                url=data["url"],
                filename=data["filename"],
            )
        if status == ResponseStatus.LOCAL_PROCESSING:
            return LocalProcessingResponse(
                status=status,
                type=data["type"],
                service=data["service"],
                tunnel=data["tunnel"],
                output=OutputObject.from_dict(data["output"]),
                audio=AudioObject.from_dict(data["audio"]) if "audio" in data else None,
                isHLS=data.get("isHLS", False),
            )
        if status == ResponseStatus.PICKER:
            return PickerResponse(
                status=status,
                picker=[PickerItem.from_dict(i) for i in data["picker"]],
                audio=data.get("audio"),
                audioFilename=data.get("audioFilename"),
            )

        raise ValueError(f"Unknown cobalt response status: {status}")

    # ── node-aware request ────────────────────

    async def _request_on_node(
        self, base_url: str, req: CobaltRequest
    ) -> CobaltResponse:
        """Отправляет запрос на конкретную ноду."""
        assert self._session, "No session"
        async with self._session.post(
            f"{base_url}/",
            headers=self._headers(),
            json=req.to_dict(),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status not in (200, 400):
                raise CobaltHttpError(resp.status, await resp.text())
            json = await resp.json()
            print(json)
            return self._parse_response(json)

    async def request(self, req: CobaltRequest) -> CobaltResponse:
        """
        POST / с автоматическим перебором нод.

        Пробует предпочтительную ноду для сервиса первой, затем остальные.
        При успехе запоминает ноду. Если все ноды упали — CobaltAllNodesFailed.
        """
        assert self._session, "No session"

        service = _service_from_url(req.url)
        nodes = self._node_order(service)
        errors: dict[str, Exception] = {}

        for base_url in nodes:
            try:
                self.logging.info(
                    f"[cobalt] trying {base_url} for service='{service}'", type="cobalt"
                )
                resp = await self._request_on_node(base_url, req)

                # Если нода ответила ошибкой fetch/network — пробуем следующую.
                # Любая другая ошибка (неверный URL, лимит и т.д.) — возвращаем сразу,
                # смена ноды не поможет.
                if isinstance(resp, ErrorResponse):
                    if resp.error.code in _RETRYABLE_ERROR_CODES:
                        self.logging.info(
                            f"[cobalt] {base_url} returned retryable '{resp.error.code}', trying next node",
                            type="cobalt",
                        )
                        errors[base_url] = CobaltApiError(resp.error)
                        continue
                    return resp

                # Успех — запоминаем ноду для этого сервиса
                self._remember_node(service, base_url)
                return resp

            except (
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientConnectionError,
                aiohttp.ClientResponseError,
                asyncio.TimeoutError,
                CobaltApiError,
                CobaltHttpError,
            ) as e:
                self.logging.info(
                    f"[cobalt] {base_url} connection error {type(e).__name__}: {e}, trying next node",
                    type="cobalt",
                )
                errors[base_url] = e
                continue

        raise CobaltAllNodesFailed(errors)

    # ── tunnel fetch ─────────────────────────

    async def fetch_tunnel(
        self, url: str, filename: str, retries: int = 3
    ) -> DownloadedFile:
        assert self._session, "No session"
        last_exc = None
        for attempt in range(retries):
            try:
                async with self._session.get(
                    url,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        raise CobaltHttpError(resp.status, await resp.text())
                    content_length = resp.headers.get("Content-Length")
                    estimated_length = resp.headers.get("Estimated-Content-Length")
                    buf = io.BytesIO(await resp.read())
                    return DownloadedFile(
                        filename=filename,
                        content_type=resp.headers.get(
                            "Content-Type", "application/octet-stream"
                        ),
                        data=buf,
                        content_length=int(content_length) if content_length else None,
                        estimated_length=int(estimated_length)
                        if estimated_length
                        else None,
                    )
            except (
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientConnectionError,
            ) as e:
                last_exc = e
                await asyncio.sleep(1.5 * (attempt + 1))
        raise last_exc

    # ── public download API ───────────────────

    async def download(
        self,
        url: str,
        *,
        request_overrides: Optional[CobaltRequest] = None,
        raise_on_picker: bool = False,
    ) -> DownloadedFile:
        """Полный цикл: перебор нод → запрос → скачивание туннеля → DownloadedFile."""
        req = request_overrides or CobaltRequest(url=url)
        req.url = url

        resp = await self.request(req)

        if isinstance(resp, ErrorResponse):
            raise CobaltApiError(resp.error)

        if isinstance(resp, TunnelResponse):
            return await self.fetch_tunnel(resp.url, resp.filename)

        if isinstance(resp, LocalProcessingResponse):
            return await self.fetch_tunnel(resp.tunnel[0], resp.output.filename)

        if isinstance(resp, PickerResponse):
            if raise_on_picker:
                raise ValueError(
                    "cobalt returned a picker response (multiple items). "
                    "Use .request() and handle PickerResponse manually, "
                    "or pass raise_on_picker=False to get the first item."
                )
            first = resp.picker[0]
            filename = first.url.split("/")[-1].split("?")[0] or "media"
            return await self.fetch_tunnel(first.url, filename)

        raise RuntimeError(f"Unhandled response type: {type(resp)}")

    async def download_all_picker(
        self,
        url: str,
        *,
        request_overrides: Optional[CobaltRequest] = None,
    ) -> list[DownloadedFile]:
        """Скачивает все элементы из picker-ответа (галерея, слайдшоу)."""
        req = request_overrides or CobaltRequest(url=url)
        req.url = url

        resp = await self.request(req)

        if isinstance(resp, ErrorResponse):
            print(resp)
            raise CobaltApiError(resp.error)

        if isinstance(resp, PickerResponse):
            files: list[DownloadedFile] = []
            for item in resp.picker:
                filename = item.url.split("/")[-1].split("?")[0] or "media"
                files.append(await self.fetch_tunnel(item.url, filename))
            return files

        return [await self.download(url, request_overrides=request_overrides)]
