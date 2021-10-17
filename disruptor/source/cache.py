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
from typing import Deque
from collections import deque
import asyncio

from .abstract import AbstractSource, CancelDisruption, Image


class Cache(AbstractSource):
    source: AbstractSource
    cache: Deque[Image]
    fetch_errors: int

    async def prepare(self) -> None:
        self.source = AbstractSource.create(self.bot, self.config)
        self.source.log = self.log.getChild(self.source.__class__.__name__.lower())
        await self.source.prepare()
        self.cache = deque(maxlen=self.config.get("size", 5))
        initial_fetch_sleep = self.config.get("initial_fetch_sleep", 0)
        self.fetch_errors = 0
        self.log.debug(f"Fetching {self.cache.maxlen} images to fill cache")
        for i in range(self.cache.maxlen):
            await self.fetch_to_cache()
            if initial_fetch_sleep:
                await asyncio.sleep(initial_fetch_sleep)

    async def fetch_to_cache(self) -> None:
        try:
            image = await self.source.fetch()
        except CancelDisruption:
            self.log.warning("Child cancelled fetch to fill cache")
            self.fetch_errors += 1
        except Exception:
            self.log.exception("Child threw error trying to fetch image to fill cache")
            self.fetch_errors += 1
        else:
            self.cache.appendleft(image)
            self.log.debug(f"Got image for cache, size is now {len(self.cache)}")
            if self.fetch_errors > 0:
                self.log.debug("Fetching additional image after successful fetch "
                               "to cover earlier error")
                self.fetch_errors -= 1
                asyncio.create_task(self.fetch_to_cache())

    async def fetch(self) -> Image:
        try:
            image = self.cache.pop()
        except IndexError:
            self.log.error("Cache is empty, canceling disruption")
            # TODO try refetching at some point
            raise CancelDisruption()
        self.log.debug("Fetching image to refill cache")
        asyncio.create_task(self.fetch_to_cache())
        return image
