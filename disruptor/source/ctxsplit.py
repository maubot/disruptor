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
from typing import Optional, List, Tuple, ClassVar

from attr import dataclass
from mautrix.types import RoomID, UserID

from .abstract import AbstractSource, Image, DisruptionContext, CancelDisruption


@dataclass
class PartialDisruptionContext:
    room_id: Optional[RoomID] = None
    room_ids: Optional[List[RoomID]] = None
    user_id: Optional[UserID] = None
    user_ids: Optional[List[RoomID]] = None

    def matches(self, ctx: DisruptionContext) -> bool:
        if self.room_id is not None and ctx.room_id != self.room_id:
            return False
        elif self.room_ids is not None and ctx.room_id not in self.room_ids:
            return False
        if self.user_id is not None and ctx.user_id != self.user_id:
            return False
        elif self.user_ids is not None and ctx.user_id not in self.user_ids:
            return False
        return True


class ContextSplit(AbstractSource):
    type_name: ClassVar[str] = "context_split"
    sources: List[Tuple[PartialDisruptionContext, AbstractSource]]

    async def prepare(self) -> None:
        self.sources = []
        for index, source_cfg in enumerate(self.config["sources"]):
            source = AbstractSource.create(self.bot, source_cfg)
            source_name = f"{index}_{type(source).__name__.lower()}"
            source.log = self.log.getChild(source_name)
            await source.prepare()
            ctx = PartialDisruptionContext(**source_cfg["context"])
            self.sources.append((ctx, source))

    async def fetch_with_context(self, ctx: DisruptionContext) -> Image:
        for src_ctx, src in self.sources:
            if src_ctx.matches(ctx):
                return await src.fetch()
        self.log.debug("Failed to disrupt: no sources matched context")
        raise CancelDisruption()

    async def fetch(self) -> Image:
        self.log.error("Failed to disrupt: called non-context fetch on ContextSplit")
        raise CancelDisruption()
