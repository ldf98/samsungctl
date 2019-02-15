# -*- coding: utf-8 -*-
import requests
from lxml import etree
from .UPNP_Device.discover import discover as _discover
from .UPNP_Device.xmlns import strip_xmlns
from ..config import Config
from .. import wake_on_lan

import logging

logger = logging.getLogger('samsungctl')


def discover(log_level=None, timeout=5):
    services = (
        'urn:schemas-upnp-org:device:MediaRenderer:1',
        'urn:samsung.com:device:IPControlServer:1',
        'urn:dial-multiscreen-org:device:dialreceiver:1',
        'urn:samsung.com:device:MainTVServer2:1',
        'urn:samsung.com:device:RemoteControlReceiver:1',
    )

    found = []

    for host, locations in _discover(timeout, log_level, services=services):
        services = list(service for service, _ in locations)
        upnp_locations = list(location for _, location in locations)

        def get_mac():
            try:
                res = requests.get(
                    'http://{0}:8001/api/v2/'.format(host),
                    timeout=3
                )
                res = res.json()['device']
                if res['networkType'] == 'wired':
                    return wake_on_lan.get_mac_address(host)
                else:
                    return res['wifiMac'].upper()
            except (
                ValueError,
                KeyError,
                requests.HTTPError,
                requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError
            ):
                return wake_on_lan.get_mac_address(host)

        if (
            'urn:schemas-upnp-org:device:MediaRenderer:1' in services and
            'urn:samsung.com:device:IPControlServer:1' in services and
            'urn:dial-multiscreen-org:device:dialreceiver:1' in services
        ):
            method = 'websocket'
            app_id = None
            port = 8001
            mac = get_mac()

        elif (
            'urn:samsung.com:device:MainTVServer2:1' in services and
            'urn:samsung.com:device:RemoteControlReceiver:1' in services and
            'urn:schemas-upnp-org:device:MediaRenderer:1' in services and
            'urn:dial-multiscreen-org:device:dialreceiver:1' in services
        ):
            method = 'encrypted'
            port = 8080
            app_id = '12345'
            # user_id = '654321'
            mac = get_mac()
            # device_id = "7e509404-9d7c-46b4-8f6a-e2a9668ad184"

        elif (
            'urn:schemas-upnp-org:device:MediaRenderer:1' in services and
            'urn:samsung.com:device:MainTVServer2:1' in services and
            'urn:samsung.com:device:RemoteControlReceiver:1' in services
        ):
            method = 'legacy'
            app_id = None
            # user_id = None
            port = 55000
            mac = wake_on_lan.get_mac_address(host)

        elif (
            'urn:samsung.com:device:RemoteControlReceiver:1' in services and
            'urn:dial-multiscreen-org:device:dialreceiver:1' in services and
            'urn:schemas-upnp-org:device:MediaRenderer:1' in services
        ):
            method = 'websocket'
            app_id = None
            port = 8001
            mac = get_mac()
        else:
            continue

        for service, location in locations:

            if service != 'urn:schemas-upnp-org:device:MediaRenderer:1':
                continue

            response = requests.get(location)
            content = response.content.decode('utf-8')

            try:
                root = etree.fromstring(content)
            except etree.XMLSyntaxError:
                continue

            root = strip_xmlns(root)
            node = root.find('device')

            if node is None:
                continue

            description = node.find('modelDescription')
            if (
                description is None or
                description.text != 'Samsung TV DMR'
            ):
                continue

            model = node.find('modelName')
            if model is None:
                continue

            model = model.text

            uuid = node.find('UDN')

            if uuid is None:
                continue

            uuid = uuid.text.split(':')[-1]
            break
        else:
            continue

        if mac is None:
            logger.error('Unable to acquire TV\'s mac address')

        config = Config(
            host=host,
            method=method,
            upnp_locations=upnp_locations,
            model=model,
            uuid=uuid,
            mac=mac,
            app_id=app_id,
            # user_id=user_id,
            port=port,
        )

        found += [config]

    return found
