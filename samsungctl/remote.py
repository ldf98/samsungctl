# -*- coding: utf-8 -*-
import logging
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

        self.config = config
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

        if self._upnp_tv is not None:
            if hasattr(self._upnp_tv, item):
                return getattr(self._upnp_tv, item)

        if hasattr(self.remote, item):
            return getattr(self.remote, item)

        if item in self.__class__.__dict__:
            if hasattr(self.__class__.__dict__[item], 'fget'):
                return self.__class__.__dict__[item].fget(self)

        if item.isupper() and item in KEYS:
            def wrapper():
                KEYS[item](self)

            return wrapper

        raise AttributeError(item)

    def __setattr__(self, key, value):
        if key in ('_upnp_tv', 'remote', 'config'):
            object.__setattr__(self, key, value)
            
        elif key == 'name':
            self.name = value
            
        elif key in self.remote.__class__.__dict__:
            obj = self.remote.__class__.__dict__[key]
            if hasattr(obj, 'fset'):
                obj.fset(self.remote, value)

        elif self._upnp_tv is not None:
            if key in self._upnp_tv.__class__.__dict__:
                obj = self._upnp_tv.__class__.__dict__[key]
                if hasattr(obj, 'fset'):
                    obj.fset(self._upnp_tv, value)
                    
    def control(self, key):
        return self.remote.control(key)

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        if hasattr(self.remote, item):
            return getattr(self.remote, item)

        if item.isupper() and item in KEYS:
            def wrapper():
                KEYS[item](self)

            return wrapper
          
        if self._upnp_tv is not None and hasattr(self._upnp_tv, item):
          return getattr(self._upnp_tv, item)
        
        raise AttributeError(item)
