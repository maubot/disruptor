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
from typing import Optional, List

from yarl import URL

from .abstract import AbstractSource, Image


class Unsplash(AbstractSource):
    source: str
    topics: List[str]
    dimensions: Optional[str]

    async def prepare(self) -> None:
        self.source = self.config.get("source", "featured")
        self.topics = self.config.get("topics", [])
        if not self.topics and "topic" in self.config:
            self.topics = [self.config["topic"]]
        self.dimensions = self.config.get("dimensions", None)

    async def fetch(self) -> Image:
        url = URL(f"https://source.unsplash.com/{self.source}")
        if self.dimensions:
            url /= self.dimensions
        url = url.with_query({key: "true" for key in self.topics})
        return await self._reupload(url)
