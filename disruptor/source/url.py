# disruptor - A maubot plugin that disrupts monologues with cat pictures.
# Copyright (C) 2022 Tulir Asokan
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
from typing import ClassVar
from yarl import URL

from .abstract import AbstractSource, Image


class URLSource(AbstractSource):
    type_name: ClassVar[str] = "url"
    url: URL

    async def prepare(self) -> None:
        self.url = URL(self.config["url"])

    async def fetch(self) -> Image:
        return await self._reupload(self.url)
