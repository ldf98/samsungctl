# -*- coding: utf-8 -*-

import six
from . import exceptions
from .remote_legacy import RemoteLegacy
from .remote_websocket import RemoteWebsocket
from .remote_encrypted import RemoteEncrypted
from .config import Config
from .key_mappings import KEYS
from .upnp.discover import discover


class KeyWrapper(object):
    def __init__(self, remote, key):
        self.remote = remote
        self.key = key

    def __call__(self):
        self.key(self.remote)


class RemoteMeta(type):

    def __call__(cls, config):

        if isinstance(config, dict):
            config = Config(**config)

        if (
            config.upnp_locations is not None
            and not config.upnp_locations
        ):
            discover(config)

        if config.method == "legacy":
            remote = RemoteLegacy(config)
        elif config.method == "websocket":
            remote = RemoteWebsocket(config)
        elif config.method == "encrypted":
            remote = RemoteEncrypted(config)
        else:
            raise exceptions.ConfigUnknownMethod()

        for name, key in KEYS.items():
            config.__dict__[name] = KeyWrapper(config, key)

        return remote


@six.add_metaclass(RemoteMeta)
class Remote(object):

    def __init__(self, config):
        self.config = config

