# -*- coding: utf-8 -*-

import six
from . import exceptions
from .remote_legacy import RemoteLegacy
from .remote_websocket import RemoteWebsocket
from .remote_encrypted import RemoteEncrypted
from .config import Config
from .key_mappings import KEYS
from .upnp import UPNPTV
from .upnp.discover import discover


class KeyWrapper(object):
    def __init__(self, remote, key):
        self.remote = remote
        self.key = key

    def __call__(self):
        self.key(self.remote)


class RemoteMeta(type):

    def __call__(cls, conf):

        if isinstance(conf, dict):
            conf = Config(**conf)

        if conf.method == "legacy":
            remote = RemoteLegacy
        elif conf.method == "websocket":
            remote = RemoteWebsocket
        elif conf.method == "encrypted":
            remote = RemoteEncrypted
        else:
            raise exceptions.ConfigUnknownMethod()

        class RemoteWrapper(remote, UPNPTV):

            def __init__(self, config):
                self.__name__ = config.name
                self._connected = False
                self._devices = {}
                self._services = {}

                for name, key in KEYS.items():
                    self.__dict__[name] = KeyWrapper(self, key)

                super(remote, self).__init__(config)

                if (
                    config.upnp_locations is not None
                    and not config.upnp_locations
                ):
                    discover(config)

                if config.upnp_locations:
                    self._upnp_started = True
                    super(UPNPTV, self).__init__(
                        config.host,
                        config.upnp_locations
                    )
                else:
                    self._upnp_started = False

                if config.path:
                    config.save()

            def __getattr__(self, item):
                if item in self.__dict__:
                    return self.__dict__[item]

                if item in remote.__dict__:
                    obj = remote.__dict__[item]
                    if hasattr(obj, 'fget'):
                        return obj.fget(self)

                if self._upnp_started:
                    if item in self._devices:
                        return self._device[item]

                    if item in self._services:
                        return self._services[item]

                    if item in UPNPTV.__dict__:
                        obj = UPNPTV.__dict__[item]
                        if hasattr(obj, 'fget'):
                            return obj.fget(self)

                raise AttributeError(item)

            def __enter__(self):
                self.open()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.close()

        return RemoteWrapper(conf)


@six.add_metaclass(RemoteMeta)
class Remote(object):

    def __init__(self, config):
        self.config = config

