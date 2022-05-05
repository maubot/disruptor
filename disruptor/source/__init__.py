from .abstract import AbstractSource, CancelDisruption
from .url import URL
from .unsplash import Unsplash
from .reddit import Reddit
from .cache import Cache
from .random import Random

for source in AbstractSource.__subclasses__():
    AbstractSource.all[(source.type_name or source.__name__).lower()] = source

__all__ = ["AbstractSource", "CancelDisruption"]
