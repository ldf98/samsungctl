# -*- coding: utf-8 -*-
from __future__ import print_function
import requests
import atexit
import socket
import json
import threading
import logging
from lxml import etree
from .UPNP_Device.xmlns import strip_xmlns
from .UPNP_Device import adapter_addresses
from ..config import Config
from .. import wake_on_lan


logger = logging.getLogger(__name__)


IPV4_MCAST_GRP = "239.255.255.250"

IPV4_SSDP = '''\
M-SEARCH * HTTP/1.1\r
ST: {0}\r
MAN: "ssdp:discover"\r
HOST: 239.255.255.250:1900\r
MX: 1\r
Content-Length: 0\r
\r
'''

SERVICES = (
    'urn:schemas-upnp-org:device:MediaRenderer:1',
    'urn:samsung.com:device:IPControlServer:1',
    'urn:dial-multiscreen-org:device:dialreceiver:1',
    'urn:samsung.com:device:MainTVServer2:1',
    'urn:samsung.com:device:RemoteControlReceiver:1',
)


def convert_ssdp_response(packet, addr):
    packet_type, packet = packet.decode('utf-8').split('\n', 1)
    if '200 OK' in packet_type:
        packet_type = 'response'
    elif 'MSEARCH' in packet_type:
        packet_type = 'search'
    elif 'NOTIFY' in packet_type:
        packet_type = 'notify'
    else:
        packet_type = 'unknown'

    packet = dict(
        (
            line.split(':', 1)[0].strip().upper(),
            line.split(':', 1)[1].strip()
        ) for line in packet.split('\n') if line.strip()
    )

    packet['TYPE'] = packet_type

    return packet


def get_mac(host):
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


class UPNPDiscoverSocket(threading.Thread):

    def __init__(self, parent, local_address, _logging):
        self._local_address = local_address
        self._parent = parent
        self.logging = _logging
        self._event = threading.Event()
        sock = self.sock = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((local_address, 0))
            sock.settimeout(5.0)
        except socket.error:
            try:
                sock.close()
            except socket.error:
                pass

            self.sock = None
        threading.Thread.__init__(self)

    def start(self):
        if self.sock is not None:
            threading.Thread.start(self)

    def run(self):

        while not self._event.isSet():
            for service in SERVICES:
                packet = IPV4_SSDP.format(service)
                if self.logging:
                    logger.debug(
                        'SSDP: %s\n%s',
                        IPV4_MCAST_GRP,
                        packet
                    )

                try:
                    self.sock.sendto(
                        packet.encode('utf-8'),
                        (IPV4_MCAST_GRP, 1900)
                    )
                except socket.error:
                    print(self._local_address)
                    import traceback
                    traceback.print_exc()
                    try:
                        self.sock.close()
                    except socket.error:
                        pass

                    self.sock = None
                    return

            found = {}
            try:
                while not self._event.isSet():
                    data, addr = self.sock.recvfrom(1024)
                    packet = convert_ssdp_response(data, addr[0])

                    if (
                        packet['TYPE'] != 'response' or
                        'LOCATION' not in packet
                    ):
                        continue

                    if (
                        packet['LOCATION'].count('/') == 2 and
                        packet['LOCATION'].startswith('http')
                    ):
                        continue

                    if self.logging:
                        logger.debug(
                            addr[0] +
                            ' --> ' +
                            self._local_address +
                            ' (SSDP)'
                        )
                        logger.debug(json.dumps(packet, indent=4))

                    if addr[0] not in found:
                        found[addr[0]] = set()

                    found[addr[0]].add((packet['ST'], packet['LOCATION']))

            except socket.timeout:
                self._parent.callback(
                    dict((addr, packet) for addr, packet in found.items())
                )
                if self.logging:
                    logger.debug(
                        self._local_address +
                        ' -- (SSDP) loop restart'
                    )
            except socket.error:
                break

        try:
            self.sock.close()
        except socket.error:
            pass

        self.sock = None

    def stop(self):
        if self.sock is not None:
            self._event.set()
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except socket.error:
                pass

            self.join(2.0)


class Discover(object):

    def __init__(self):
        self._callbacks = []
        self._powered_on = []
        self._powered_off = []
        self._threads = []
        self._logging = False

    @property
    def logging(self):
        return self._logging

    @logging.setter
    def logging(self, value):
        self._logging = value
        for thread in self._threads:
            thread.logging = value

    def start(self):
        for adapter_ip in adapter_addresses.get_adapter_ips():
            thread = UPNPDiscoverSocket(self, adapter_ip, self._logging)
            self._threads += [thread]
            thread.start()

        atexit.register(self.stop)

    def is_on(self, uuid):
        for config in self._powered_on:
            if config.uuid == uuid:
                return config

    def stop(self):
        del self._callbacks[:]

        while self._threads:
            thread = self._threads.pop(0)
            thread.stop()

        try:
            atexit.unregister(self.stop)
        except (NameError, AttributeError):
            pass

    def register_callback(self, callback, uuid=None):
        self._callbacks += [(callback, uuid)]

        for config in self._powered_on:
            if config.uuid == uuid:
                return config, True

        for config in self._powered_off:
            if config.uuid == uuid:
                return config, False

        return None, None

    def get_discovered(self):
        return self._powered_on[:] + self._powered_off[:]

    def unregister_callback(self, callback, uuid=None):
        if (callback, uuid) in self._callbacks:
            self._callbacks.remove((callback, uuid))

    def callback(self, found):
        if self._logging:
            logging.debug(str(found))
        powered_on = []
        for host, packet in found.items():
            services = list(service for service, _ in packet)
            upnp_locations = list(location for _, location in packet)

            for service, location in packet:
                if service != 'urn:schemas-upnp-org:device:MediaRenderer:1':
                    continue

                if self.logging:
                    logger.debug(
                        host +
                        ' <-- (' +
                        location +
                        ') ""'
                    )

                response = requests.get(location)

                if self.logging:
                    logger.debug(
                        host +
                        ' --> (' +
                        location +
                        ') ' +
                        response.content.decode('utf-8')
                    )

                try:
                    root = etree.fromstring(response.content.decode('utf-8'))
                except etree.ParseError:
                    continue
                except ValueError:
                    try:
                        root = etree.fromstring(response.content)
                    except etree.ParseError:
                        continue

                root = strip_xmlns(root)
                node = root.find('device')

                if node is None:
                    continue

                description = node.find('modelDescription')
                if (
                    description is None or
                    'Samsung' not in description.text or
                    'TV' not in description.text
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

                product_cap = node.find('ProductCap')
                if product_cap is None:
                    years = dict(
                        A=2008,
                        B=2009,
                        C=2010,
                        D=2011,
                        E=2012,
                        F=2013,
                        H=2014,
                        J=2015
                    )
                    year = years[model[4].upper()]
                else:
                    product_cap = product_cap.text.split(',')

                    for item in product_cap:
                        if (
                            item.upper().startswith('Y') and
                            len(item) == 5 and
                            item[1:].isdigit()
                        ):
                            year = int(item[1:])
                            break
                    else:
                        year = None
                break
            else:
                return

            if year is None:
                if (
                    'urn:schemas-upnp-org:device:MediaRenderer:1' in services and
                    'urn:samsung.com:device:IPControlServer:1' in services and
                    'urn:dial-multiscreen-org:device:dialreceiver:1' in services
                ):
                    method = 'websocket'
                    app_id = None
                    port = 8001
                    mac = get_mac(host)

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
                    mac = get_mac(host)
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
                    mac = get_mac(host)
                else:
                    return

            elif year <= 2013:
                method = 'legacy'
                app_id = None
                # user_id = None
                port = 55000
                mac = wake_on_lan.get_mac_address(host)

            elif year <= 2015:
                method = 'encrypted'
                port = 8080
                app_id = '12345'
                # user_id = '654321'
                mac = get_mac(host)
                # device_id = "7e509404-9d7c-46b4-8f6a-e2a9668ad184"

            else:
                method = 'websocket'
                app_id = None
                port = 8001
                mac = get_mac(host)

            config1 = Config(
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

            for config2 in self._powered_off:
                if config2 == config1:
                    self._powered_off.remove(config2)
                    self._powered_on += [config1]
                    for callback, uuid in self._callbacks:
                        if uuid is None:
                            continue

                        if uuid == config1.uuid:
                            callback(config1, True)

            for config2 in self._powered_on:
                if config1 == config2:
                    break
            else:
                for callback, uuid in self._callbacks:
                    if uuid is None:
                        if mac is None:
                            logger.warning(
                                'Unable to acquire TV\'s mac address'
                            )

                        callback(config1)
                    elif uuid == config1.uuid:
                        callback(config1, True)

            powered_on += [config1]

        for config2 in self._powered_on[:]:
            for config1 in powered_on:
                if config1 == config2:
                    break
            else:
                self._powered_on.remove(config2)
                self._powered_off += [config2]
                for callback, uuid in self._callbacks:
                    if uuid is None:
                        continue

                    if uuid == config2.uuid:
                        callback(config2, False)

    @property
    def is_running(self):
        if self._threads:
            return True
        return False


auto_discover = Discover()


def discover(host=None, timeout=6):

    if timeout < 6:
        timeout = 6
    event = threading.Event()

    def discover_callback(config):
        configs.append(config)

    if not auto_discover.is_running:
        configs = []
        auto_discover.register_callback(discover_callback)
        auto_discover.start()
        event.wait(timeout)
        auto_discover.stop()
    else:
        configs = auto_discover.get_discovered()
        auto_discover.register_callback(discover_callback)
        event.wait(timeout)
        auto_discover.unregister_callback(discover_callback)

    if host:
        for config in configs:
            if config.host == host:
                return [config]

        return []

    return configs
