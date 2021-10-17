from .abstract import AbstractSource, CancelDisruption
from .unsplash import Unsplash
from .reddit import Reddit
from .cache import Cache

for source in AbstractSource.__subclasses__():
    AbstractSource.all[source.__name__.lower()] = source

__all__ = ["AbstractSource", "CancelDisruption"]
