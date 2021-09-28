# catdisruptor - A maubot plugin that disrupts monologues with cat pictures.
# Copyright (C) 2019 Tulir Asokan
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
from typing import Dict, Set, List, Type, Tuple, Optional
from collections import defaultdict
from time import time
import asyncio

from attr import dataclass
import magic
import aiohttp

from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from mautrix.types import (EventType, UserID, RoomID, MediaMessageEventContent, ImageInfo,
                           ThumbnailInfo, ContentURI, MessageType, GenericEvent,
                           BaseMessageEventContent)

from maubot import Plugin, MessageEvent
from maubot.handlers import event, command

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    Image = None
    BytesIO = None


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("subreddits")
        helper.copy("min_monologue_size")
        helper.copy("max_monologue_delay")
        helper.copy("disrupt_cooldown")
        helper.copy("user_agent")
        helper.copy("user_ratelimit.rate")
        helper.copy("user_ratelimit.per")
        helper.copy("user_ratelimit.message")
        helper.copy("room_ratelimit.rate")
        helper.copy("room_ratelimit.per")
        helper.copy("room_ratelimit.message")


class MonologueInfo:
    user_id: Optional[UserID]
    streak: int
    last_message: float
    prev_disrupt: float
    lock: asyncio.Lock

    def __init__(self, user_id: Optional[UserID] = None, streak: int = 0, last_message: float = 0,
                 prev_disrupt: float = 0) -> None:
        self.user_id = user_id
        self.streak = streak
        self.last_message = last_message
        self.prev_disrupt = prev_disrupt
        self.lock = asyncio.Lock()

    def message(self, user_id: UserID) -> None:
        if self.user_id == user_id:
            self.streak += 1
        else:
            self.user_id = user_id
            self.streak = 1
        self.last_message = time()

    def reset(self) -> None:
        self.user_id = None
        self.streak = 0

    def is_outdated(self, max_delay: int) -> bool:
        return self.last_message != 0 and self.last_message + max_delay < time()

    def should_disrupt(self, min_count: int, disrupt_cooldown: int) -> bool:
        return self.streak >= min_count and self.prev_disrupt + disrupt_cooldown < time()

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"MonologueInfo(user_id={self.user_id}, streak={self.streak}, last_message={self.last_message}, prev_disrupt={self.prev_disrupt})"


@dataclass
class ManualRateLimit:
    rate: float = 3.0
    per: float = 3600.0
    allowance: float = 0.0
    last_request: float = 0.0

    def __attrs_post_init__(self) -> None:
        self.allowance = self.rate

    def request(self) -> bool:
        now = time()
        time_passed = now - self.last_request
        self.last_request = now
        self.allowance += time_passed * (self.rate / self.per)
        if self.allowance > self.rate:
            self.allowance = self.rate
        if self.allowance < 1.0:
            return False
        else:
            self.allowance -= 1.0
            return True


class DisruptorBot(Plugin):
    monologue_size: Dict[RoomID, MonologueInfo]
    manual_room_ratelimits: Dict[RoomID, ManualRateLimit]
    manual_user_ratelimits: Dict[UserID, ManualRateLimit]
    cache: List[dict]
    handled_ids: Set[str]
    reload_lock: asyncio.Lock

    async def start(self):
        await super().start()
        self.config.load_and_update()

        self.monologue_size = defaultdict(lambda: MonologueInfo())
        self.manual_room_ratelimits = defaultdict(lambda: ManualRateLimit(
            rate=float(self.config["room_ratelimit.rate"]),
            per=float(self.config["room_ratelimit.per"])))
        self.manual_user_ratelimits = defaultdict(lambda: ManualRateLimit(
            rate=float(self.config["user_ratelimit.rate"]),
            per=float(self.config["user_ratelimit.per"])))
        self.cache = []
        self.handled_ids = set()
        self.reload_lock = asyncio.Lock()

        await self.load_disruption_content()

    async def fetch_posts(self, subreddit: str) -> dict:
        resp = await self.http.get(f"https://www.reddit.com/r/{subreddit}/.json?raw_json=1",
                                   headers={"User-Agent": self.config["user_agent"]})
        try:
            return await resp.json()
        except aiohttp.ContentTypeError:
            self.log.error("Got non-JSON response data with status %s while trying to find pictures", resp.status)
            return {"data": {"children": []}}

    async def reload_disruption_content(self) -> None:
        async with self.reload_lock:
            if len(self.cache) < 5:
                await self.load_disruption_content()

    async def load_disruption_content(self) -> None:
        for subreddit in self.config["subreddits"]:
            self.log.debug(f"Caching data from {subreddit}...")
            n = 0
            listing = await self.fetch_posts(subreddit)
            for post in listing["data"]["children"]:
                data = post["data"]
                if (data.get("post_hint", "") == "image"
                        and not data.get("over_18", False)
                        and data["id"] not in self.handled_ids):
                    self.handled_ids.add(data["id"])
                    self.cache.append({
                        "image": data["url"],
                        "thumbnail": {
                            "url": data["thumbnail"],
                            "width": data["thumbnail_width"],
                            "height": data["thumbnail_height"],
                        },
                        "link": "https://www.reddit.com" + data["permalink"],
                        "title": data["title"],
                    })
                    n += 1
            self.log.info(f"{n} posts cached from {subreddit}")

    @event.on(EventType.ROOM_ENCRYPTED)
    async def encrypted_monologue_detector(self, evt: GenericEvent) -> None:
        await self.monologue_detector(evt)

    @event.on(EventType.ROOM_MESSAGE)
    async def monologue_detector(self, evt: MessageEvent) -> None:
        if isinstance(evt.content, BaseMessageEventContent) and evt.content.get_edit():
            return
        monologue = self.monologue_size[evt.room_id]
        if monologue.is_outdated(self.config["max_monologue_delay"]):
            monologue.reset()
        monologue.message(evt.sender)
        async with monologue.lock:
            if monologue.should_disrupt(self.config["min_monologue_size"],
                                        self.config["disrupt_cooldown"]):
                self.log.debug(f"Disrupting monologue in {evt.room_id}: {monologue}")
                await self.disrupt(evt.room_id)
                monologue.reset()

    async def reupload(self, url: str) -> Tuple[ContentURI, str, bytes]:
        resp = await self.http.get(url, headers={"User-Agent": self.config["user_agent"]})
        data = await resp.read()
        mime_type = magic.from_buffer(data, mime=True)
        mxc = await self.client.upload_media(data, mime_type)
        return mxc, mime_type, data

    @command.passive(r"^\U0001f408\ufe0f?$")
    async def cat_command(self, evt: MessageEvent, _: str) -> None:
        if self.manual_user_ratelimits[evt.sender].request():
            if self.manual_room_ratelimits[evt.room_id].request():
                await self.disrupt(evt.room_id)
            else:
                await evt.reply(self.config["room_ratelimit.message"])
                self.manual_user_ratelimits[evt.sender].allowance += 1
        else:
            await evt.reply(self.config["user_ratelimit.message"])

    async def disrupt(self, room_id: RoomID) -> None:
        if len(self.cache) == 0:
           self.log.warning("Cache is empty, awaiting reload")
           await self.reload_disruption_content()
        if len(self.cache) == 0:
           self.log.error("Failed to disrupt: cache is still empty after reload")
           return
        disruption_content = self.cache.pop()
        if len(self.cache) < 5:
            asyncio.create_task(self.reload_disruption_content())
        mxc, mime, data = await self.reupload(disruption_content["image"])
        tn_mxc, tn_mime, tn_data = await self.reupload(disruption_content["thumbnail"]["url"])
        info = ImageInfo(
            size=len(data),
            mimetype=mime,
            thumbnail_url=tn_mxc,
            thumbnail_info=ThumbnailInfo(
                mimetype=tn_mime,
                size=len(tn_data),
                width=disruption_content["thumbnail"]["width"],
                height=disruption_content["thumbnail"]["height"],
            ),
        )
        if Image is not None:
            img = Image.open(BytesIO(data))
            info.width, info.height = img.size
        await self.client.send_message_event(
            room_id, EventType.ROOM_MESSAGE, MediaMessageEventContent(
                url=mxc, info=info, msgtype=MessageType.IMAGE,
                body=disruption_content["title"]))

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
