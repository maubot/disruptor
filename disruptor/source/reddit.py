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
from typing import Set, List
import asyncio

from yarl import URL
import aiohttp

from mautrix.util import background_task

from .abstract import AbstractSource, Image, CancelDisruption


class Reddit(AbstractSource):
    reload_lock: asyncio.Lock
    subreddit: str
    handled_ids: Set[str]
    cache: List[dict]

    async def prepare(self) -> None:
        self.reload_lock = asyncio.Lock()
        self.handled_ids = set()
        self.subreddit = self.config["subreddit"]

    async def fetch_posts(self, subreddit: str) -> list:
        resp = await self.bot.http.get(f"https://www.reddit.com/r/{subreddit}/.json?raw_json=1",
                                       headers={"User-Agent": self.config["user_agent"]})
        try:
            data = await resp.json()
        except aiohttp.ContentTypeError:
            self.log.error(
                "Got non-JSON response data with status %s while trying to find pictures",
                resp.status)
            return []
        return data["data"]["children"]

    async def load_disruption_content(self) -> None:
        self.log.debug(f"Caching data from {self.subreddit}...")
        n = 0
        listing = await self.fetch_posts(self.subreddit)
        for post in listing:
            data = post["data"]
            if (data.get("post_hint", "") == "image"
                    and not data.get("over_18", False)
                    and data["id"] not in self.handled_ids):
                self.handled_ids.add(data["id"])
                self.cache.append({
                    "url": URL(data["url"]),
                    "thumbnail_url": URL(data["thumbnail"]),
                    "thumbnail_dimensions": (data["thumbnail_width"], data["thumbnail_height"]),
                    "external_url": "https://www.reddit.com" + data["permalink"],
                    "title": data["title"],
                })
                n += 1
        self.log.info(f"{n} posts cached from {self.subreddit}")

    async def reload_disruption_content(self) -> None:
        async with self.reload_lock:
            if len(self.cache) < 5:
                await self.load_disruption_content()

    async def fetch(self) -> Image:
        if len(self.cache) == 0:
            self.log.warning("Cache is empty, awaiting reload")
            await self.reload_disruption_content()
        if len(self.cache) == 0:
            self.log.error("Failed to disrupt: cache is still empty after reload")
            raise CancelDisruption()
        disruption_content = self.cache.pop()
        if len(self.cache) < 5:
            background_task.create(self.reload_disruption_content())
        return await self._reupload(**disruption_content["image"])
