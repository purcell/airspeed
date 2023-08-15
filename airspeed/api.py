import os

from cachetools import LRUCache

from airspeed.operators import CachingFileLoader

__all__ = ["Airspeed"]


class Airspeed(object):
    def __init__(self, cache=10, **kw):
        self.loaders = LRUCache(maxsize=cache)

    def __call__(self, data, template, mime_type="text/plain", **options):
        basepath = os.path.dirname(template)

        if basepath not in self.loaders:
            loader = CachingFileLoader(basepath)
            self.loaders[basepath] = loader

        else:
            loader = self.loaders[basepath]

        template = self.loaders[basepath].load_template(os.path.basename(template))

        return mime_type, template.merge(data, loader=loader)
