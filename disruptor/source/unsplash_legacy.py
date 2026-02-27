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
import time
from yarl import URL

from .url import URLSource, AbstractSource


class UnsplashLegacy(URLSource, AbstractSource):
    type_name = "unsplash"

    async def prepare(self) -> None:
        # source.unsplash.com has been discontinued.
        # We replace it with loremflickr.com as a fallback to prevent breakage.
        url_str = "https://loremflickr.com"

        dimensions = self.config.get("dimensions", "800x600")
        if dimensions:
            dimensions = dimensions.replace("x", "/")
            url_str += f"/{dimensions}"

        topics = self.config.get("topics", [])
        if not topics and "topic" in self.config:
            topics = [self.config["topic"]]

        if topics:
            # Unsplash topics were often format "animals/cat". Extract last part.
            keywords = ",".join(t.split("/")[-1] for t in topics)
            url_str += f"/{keywords}"

        self.url = URL(url_str)

    async def fetch(self):
        # Override fetch to append a random query param to circumvent caching
        return await self._reupload(self.url.with_query({"random": str(time.time())}))