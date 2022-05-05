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
from __future__ import annotations

import random

from .abstract import AbstractSource, Image, DisruptionContext


class Random(AbstractSource):
    sources: list[AbstractSource]
    weights: list[float]

    async def prepare(self) -> None:
        self.sources = []
        int_weights: list[int] = []
        for index, source_cfg in enumerate(self.config["sources"]):
            source = AbstractSource.create(self.bot, source_cfg)
            source_name = f"{index}_{type(source).__name__.lower()}"
            source.log = self.log.getChild(source_name)
            await source.prepare()
            self.sources.append(source)
            int_weights.append(source_cfg["weight"])
        weight_sum = sum(int_weights)
        self.weights = [weight / weight_sum for weight in int_weights]

    async def fetch_with_context(self, ctx: DisruptionContext | None = None) -> Image:
        source = random.choices(self.sources, self.weights, k=1)[0]
        return await source.fetch_with_context(ctx)

    async def fetch(self) -> Image:
        return await self.fetch_with_context(None)
