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
from yarl import URL

from .url import URLSource, AbstractSource


class UnsplashLegacy(URLSource, AbstractSource):
    type_name = "unsplash"

    async def prepare(self) -> None:
        source = self.config.get("source", "featured")
        url = URL("https://source.unsplash.com") / source

        dimensions = self.config.get("dimensions", None)
        if dimensions:
            url /= dimensions

        topics = self.config.get("topics", [])
        if not topics and "topic" in self.config:
            topics = [self.config["topic"]]
        self.url = url.with_query({key: "true" for key in topics})
