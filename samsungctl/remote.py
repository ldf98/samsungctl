# -*- coding: utf-8 -*-
from . import exceptions
from .remote_legacy import RemoteLegacy
from .remote_websocket import RemoteWebsocket
from .config import Config
from .key_mappings import KEYS
from .upnp import UPNPTV
from .upnp.UPNP_Device.discover import discover


try:
    from .remote_encrypted import RemoteEncrypted
except ImportError:
    RemoteEncrypted = None


class Remote(object):
    def __init__(self, config):
        self._upnp_tv = None
        self.config = config
        self.remote = None

        if isinstance(config, dict):
            config = Config(**config)

        if config.method == "legacy":
            self.remote = RemoteLegacy(config)
        elif config.method == "websocket":
            self.remote = RemoteWebsocket(config)
        elif config.method == "encrypted":
            if RemoteEncrypted is None:
                raise RuntimeError(
                    'Python 2 is not currently supported '
                    'for H and J model year TV\'s'
                )

            self.remote = RemoteEncrypted(config)
        else:
            raise exceptions.ConfigUnknownMethod()

    def connect_upnp(self):
        if self._upnp is None:
            if not self.config.upnp_locations:
                devices = discover(self.config.host)
                if devices:
                    self.config.upnp_locations = devices[0][1]

            if self.config.upnp_locations:
                self._upnp_tv = UPNPTV(
                    self.config.host,
                    self.config.upnp_locations,
                    self
                )

    @property
    def upnp_tv(self):
        return self._upnp_tv

    @property
    def name(self):
        return self.config.name

    @name.setter
    def name(self, value):
        self.config.name = value

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def open(self):
        self.remote.open()

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        if hasattr(self.remote, item):
            return getattr(self.remote, item)

        if item in self.__class__.__dict__:
            if hasattr(self.__class__.__dict__[item], 'fget'):
                return self.__class__.__dict__[item].fget(self)

        if item.isupper() and item in KEYS:
            def wrapper():
                KEYS[item](self)

            return wrapper

        if self._upnp_tv is None:
            self.connect_upnp()

        if self._upnp_tv is not None:
            if item in self._upnp_tv.__class__.__dict__:
                if hasattr(self._upnp_tv.__class__.__dict__[item], 'fget'):
                    return self._upnp_tv.__class__.__dict__[item].fget(self._upnp_tv)

        raise AttributeError(item)

    def __setattr__(self, key, value):
        if key in ('_upnp_tv', 'remote', 'config'):
            object.__setattr__(self, key, value)
            return

        if key == 'name':
            self.name = value
            return

        if key in self.remote.__class__.__dict__:
            obj = self.remote.__class__.__dict__[key]
            if hasattr(obj, 'fset'):
                obj.fset(self.remote, value)
                return

        if hasattr(self.remote, key):
            setattr(self.remote, key, value)
            return

        if self._upnp_tv is None:
            self.connect_upnp()

        if self._upnp_tv is not None:
            if key in self._upnp_tv.__class__.__dict__:
                obj = self._upnp_tv.__class__.__dict__[key]
                if hasattr(obj, 'fset'):
                    obj.fset(self._upnp_tv, value)

    def control(self, key):
        return self.remote.control(key)
