from .abstract import AbstractSource, CancelDisruption, DisruptionContext
from .unsplash import Unsplash
from .reddit import Reddit
from .cache import Cache
from .random import Random
from .ctxsplit import ContextSplit
from .noop import Noop

for source in AbstractSource.__subclasses__():
    AbstractSource.all[(source.type_name or source.__name__).lower()] = source

__all__ = ["AbstractSource", "CancelDisruption", "DisruptionContext"]
