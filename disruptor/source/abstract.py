# disruptor - A maubot plugin that disrupts monologues with cat pictures.
# Copyright (C) 2021 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import NamedTuple, Tuple, Type, Optional, Dict, Any, ClassVar, TYPE_CHECKING
from abc import ABC, abstractmethod
from io import BytesIO
import mimetypes
import cgi

from aiohttp import ClientResponse
from yarl import URL
import magic

from mautrix.types import ImageInfo, ContentURI, UserID, RoomID
from mautrix.util.logging import TraceLogger

try:
    from PIL import Image as Pillow
except ImportError:
    Pillow = None

if TYPE_CHECKING:
    from ..bot import DisruptorBot


class Image(NamedTuple):
    title: str
    url: ContentURI
    info: ImageInfo
    external_url: str


class CancelDisruption(Exception):
    pass


class DisruptionContext(NamedTuple):
    room_id: RoomID
    user_id: UserID


class AbstractSource(ABC):
    type_name: ClassVar[str] = None
    all: ClassVar[Dict[str, Type['AbstractSource']]] = {}
    bot: 'DisruptorBot'
    log: TraceLogger
    config: Dict[str, Any]

    def __init__(self, bot: 'DisruptorBot', config: Dict[str, Any]) -> None:
        self.bot = bot
        self.log = bot.log.getChild("source").getChild(self.__class__.__name__.lower())
        self.config = config

    async def prepare(self) -> None:
        pass

    async def fetch_with_context(self, ctx: DisruptionContext) -> Image:
        return await self.fetch()

    @abstractmethod
    async def fetch(self) -> Image:
        pass

    @classmethod
    def create(cls, bot: 'DisruptorBot', config: Dict[str, Any]
                     ) -> 'AbstractSource':
        type_cls = cls.all[config["type"].lower()]
        return type_cls(bot, config.get("config", {}))

    @staticmethod
    def _get_filename(url: URL, resp: ClientResponse, mimetype: str) -> str:
        filename = None
        try:
            _, params = cgi.parse_header(resp.headers["Content-Disposition"])
            filename = params.get("filename")
        except KeyError:
            pass
        if not filename:
            filename = (resp.url or url).path.split("/")[-1]
        if "." not in filename:
            filename += mimetypes.guess_extension(mimetype) or ""
        return filename

    async def _reupload(self, url: URL, title: Optional[str] = None, blurhash: Optional[str] = None,
                        dimensions: Optional[Tuple[int, int]] = None,
                        external_url: Optional[str] = None,
                        thumbnail_url: Optional[URL] = None,
                        thumbnail_dimensions: Optional[Tuple[int, int]] = None,
                        headers: Optional[Dict[str, str]] = None) -> Image:
        self.log.debug(f"Reuploading {title} from {url}")
        info = ImageInfo()
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config["user_agent"]
        async with self.bot.http.get(url, headers=headers) as resp:
            data = await resp.read()
            info.size = len(data)
            info.mimetype = resp.headers["Content-Type"]
            if not info.mimetype:
                info.mimetype = magic.from_buffer(data, mime=True)
            if not title:
                title = self._get_filename(url, resp, info.mimetype)
        if dimensions:
            info.width, info.height = dimensions
        elif Pillow:
            img = Pillow.open(BytesIO(data))
            info.width, info.height = img.size
        mxc = await self.bot.client.upload_media(data, info.mimetype)
        if thumbnail_url:
            thumbnail = await self._reupload(thumbnail_url, title=title, headers=headers,
                                             dimensions=thumbnail_dimensions)
            info.thumbnail_url = thumbnail.url
            info.thumbnail_info = thumbnail.info
        if blurhash:
            info["blurhash"] = blurhash
            info["xyz.amorgan.blurhash"] = blurhash
        return Image(url=mxc, info=info, title=title, external_url=external_url)
