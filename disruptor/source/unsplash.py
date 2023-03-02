# disruptor - A maubot plugin that disrupts monologues with cat pictures.
# Copyright (C) 2023 Tulir Asokan
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
from __future__ import annotations

import time
from collections import deque
import asyncio

from yarl import URL
from mautrix.util import background_task

from .abstract import AbstractSource, Image, CancelDisruption


class Unsplash(AbstractSource):
    type_name = "unsplash2"
    cache: deque[Image]
    min_cache_size: int
    fetch_count: int
    api_url: URL
    cache_lock: asyncio.Lock
    size_name: str
    thumb_size_name: str
    next_refill_allowed: float
    access_key: str

    async def prepare(self) -> None:
        self.access_key = self.config["access_key"]
        self.min_cache_size = self.config.get("min_cache_size", 10)
        self.fetch_count = self.config.get("fetch_count", 30)
        self.size_name = self.config.get("size_name", "regular")
        self.thumb_size_name = self.config.get("thumb_size_name", "thumb")
        self.cache = deque(maxlen=self.min_cache_size+self.fetch_count)
        self.next_refill_allowed = 0
        search_query = self.config.get("query")
        orientation = self.config.get("orientation")
        query_params = {"count": str(self.fetch_count)}
        if search_query:
            query_params["query"] = search_query
        if orientation:
            query_params["orientation"] = orientation
        self.cache_lock = asyncio.Lock()
        self.api_url = URL("https://api.unsplash.com/photos/random").with_query(query_params)
        await self._refill_cache()

    async def _refill_cache(self) -> None:
        try:
            async with self.cache_lock:
                if len(self.cache) > self.min_cache_size:
                    return
                await self._try_refill_cache()
        except Exception:
            self.log.exception("Failed to refill cache")

    async def _try_refill_cache(self) -> None:
        if self.next_refill_allowed > time.monotonic():
            self.log.debug("Not refilling cache, low on ratelimit")
            return
        headers = {}
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config["user_agent"]
        headers["Authorization"] = f"Client-ID {self.access_key}"
        self.log.info(f"Refilling cache (current size: {len(self.cache)})")
        async with self.bot.http.get(self.api_url, headers=headers) as resp:
            data = await resp.json()
            if resp.status >= 400:
                self.log.error(f"Failed to refill cache: HTTP {resp.status}: {data}")
                resp.raise_for_status()
            if int(resp.headers["x-ratelimit-remaining"]) < 10:
                self.log.debug("Low on ratelimit, marking next refill as only allowed in an hour")
                self.next_refill_allowed = time.monotonic() + 60 * 60
            for image_info in data:
                download_url = URL(image_info["urls"][self.size_name])
                dimensions = (image_info["width"], image_info["height"]) if self.size_name in ("raw", "full") else None
                external_url = image_info["links"]["html"]
                image = await self._reupload(
                    download_url,
                    title=image_info["id"] + ".jpg",
                    blurhash=image_info.get("blur_hash", None),
                    dimensions=dimensions,
                    external_url=external_url,
                    thumbnail_url=image_info["urls"][self.thumb_size_name],
                    headers=headers,
                )
                self.cache.appendleft(image)
        self.log.info(f"Cache refilled, now have {len(self.cache)} images")

    async def fetch(self) -> Image:
        if len(self.cache) < self.min_cache_size:
            background_task.create(self._refill_cache())
        try:
            return self.cache.pop()
        except IndexError:
            self.log.error("Cache is empty, canceling disruption")
            raise CancelDisruption()
