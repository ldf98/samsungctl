# -*- coding: utf-8 -*-
import socket
import requests
from lxml import etree
from .UPNP_Device.discover import discover as _discover
from .UPNP_Device.xmlns import strip_xmlns
from . import UPNPTV
from ..config import Config
from ..remote import Remote


def discover(config=None, log_level=None):
    if config is None:
        remotes = []
        for ip, locations in _discover(5, log_level):
            location = locations[0]
            response = requests.get(location)
            root = etree.fromstring(response.content)

            root = strip_xmlns(root)

            device = root.find('device')
            mfgr = device.find('manufacturer').text
            if mfgr == 'Samsung Electronics':
                upnp_tv = UPNPTV(ip, locations, None)
                description = socket.gethostname()
                if hasattr(upnp_tv, 'ScreenSharingService'):
                    port = 8001
                    method = 'websocket'
                else:
                    port = 55000
                    method = 'legacy'

                host = ip
                config = Config(
                    host=host,
                    name=upnp_tv.__name__,
                    description=description,
                    method=method,
                    port=port,
                    upnp_locations=locations
                )

                remote = Remote(config)
                remote._upnp_tv = upnp_tv
                upnp_tv._remote = remote
                remotes += [remote]
        return remotes

    if isinstance(config, dict):
        config = Config(**config)

    if config.upnp_locations:

        remote = Remote(config)
        upnp_tv = UPNPTV(config.host, config.upnp_locations, remote)
        remote._upnp_tv = upnp_tv
        return remote
    else:
        return Remote(config)
