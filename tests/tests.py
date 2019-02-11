# -*- coding: utf-8 -*-
from __future__ import print_function
import threading
import unittest
import sys
import os
import ssl
import base64
import json
import random
import string
import time
import uuid
import logging
import socket
import flask
import struct
from xml.dom.minidom import Document
from lxml import etree


try:
    import responses
    import ssdp
except ImportError:
    from . import responses
    from . import ssdp

IPV4_MCAST_GRP = '239.255.255.250'
IPV6_MCAST_GRP = '[ff02::c]'

BIND_ADDREESS = ('127.0.0.1', 1900)

'''
M-SEARCH * HTTP/1.1
ST: ssdp:all
MAN: "ssdp:discover"
HOST: 239.255.255.250:1900
MX: 10
Content-Length: 0


Received 1/22/2019 at 8:03:06 AM (40)

M-SEARCH * HTTP/1.1
ST: upnp:rootdevice
MAN: "ssdp:discover"
HOST: [ff02::c]:1900
MX: 10
Content-Length: 0


'''
BASE_PATH = os.path.abspath(os.path.dirname(__file__))
LOCAL_IP = socket.gethostbyname(socket.gethostname())
UPNP_PORT = 7272
ENVELOPE_XMLNS = 'http://schemas.xmlsoap.org/soap/envelope/'
VERBOSE = 0


data_type_classes = {
    'time.tz': str,
    'time': str,
    'dateTime.tz': str,
    'dateTime': str,
    'date': str,
    'uuid': str,
    'uri': str,
    'bin.base64': str,
    'boolean': bool,
    'string': str,
    'char': str,
    'float': float,
    'fixed.14.4': float,
    'number': int,
    'r8': float,
    'r4': float,
    'int': int,
    'i8': int,
    'i4': int,
    'i2': int,
    'i1': int,
    'ui8': int,
    'ui4': int,
    'ui2': int,
    'ui1': int,
    'long': int
}


def convert_packet(packet):
    packet_type, packet = packet.decode('utf-8').split('\n', 1)
    packet_type = packet_type.upper().split('*')[0].strip()

    packet = dict(
        (
            line.split(':', 1)[0].strip().upper(),
            line.split(':', 1)[1].strip()
        ) for line in packet.split('\n') if line.strip()
    )

    packet['TYPE'] = packet_type
    return packet


def build_xml_response(func, retvals):
    doc = Document()

    envelope = doc.createElementNS('', 'Envelope')
    body = doc.createElementNS('', 'Body')

    fn = doc.createElementNS('', func)

    for key, value in retvals:

        tmp_node = doc.createElement(key)
        tmp_text_node = doc.createTextNode(str(value))
        tmp_node.appendChild(tmp_text_node)
        fn.appendChild(tmp_node)

    body.appendChild(fn)
    envelope.appendChild(body)
    doc.appendChild(envelope)
    pure_xml = doc.toxml()
    return pure_xml


def strip_xmlns(root):
    def iter_node(n):
        nsmap = n.nsmap
        for child in n:
            nsmap.update(iter_node(child))
        return nsmap

    xmlns = list('{' + item + '}' for item in iter_node(root).values())

    def strip_node(n):
        for item in xmlns:
            n.tag = n.tag.replace(item, '')

        for child in n[:]:
            try:
                strip_node(child)
            except AttributeError:
                n.remove(child)
    strip_node(root)

    return root


for arg in list(sys.argv):
    if arg.startswith('-v'):
        VERBOSE = arg.count('v')

if VERBOSE == 1:
    LOG_LEVEL = logging.INFO
elif VERBOSE == 2:
    LOG_LEVEL = logging.DEBUG
else:
    LOG_LEVEL = logging.ERROR
LOG_LEVEL = logging.DEBUG
URL_FORMAT = "ws://{}:{}/api/v2/channels/samsung.remote.control?name={}"
SSL_URL_FORMAT = "wss://{}:{}/api/v2/channels/samsung.remote.control?name={}"
TOKEN = ''.join(
    random.choice(string.digits + string.ascii_letters) for _ in range(20)
)

APP_NAMES = list(
    app['name'] for app in responses.INSTALLED_APP_RESPONSE['data']['data']
)
APP_IDS = list(
    app['appId'] for app in responses.INSTALLED_APP_RESPONSE['data']['data']
)

APP_NAMES += list(
    app['name'] for app in responses.EDEN_APP_RESPONSE['data']['data']
    if app['name'] not in APP_NAMES
)
APP_IDS += list(
    app['id'] for app in responses.EDEN_APP_RESPONSE['data']['data']
    if app['id'] not in APP_IDS
)


def key_wrapper(func):
    key = func.__name__.split('_', 2)[-1]

    def wrapper(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.remote.control',
                params=dict(
                    Cmd='Click',
                    DataOfCmd=key,
                    Option="false",
                    TypeOfRemote="SendRemoteKey"
                )
            )
            self.assertEqual(expected_message, message)
            event.set()

        self.client.on_message = on_message

        self.remote.control(key)
        event.wait(1)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    return wrapper

class FakeWebsocketClient(object):
    def __init__(self, handler):

        self.url = None
        self.sslopt = None
        self.enable_multithread = None
        self.handler = handler
        self.callback = None
        self.return_data = []
        self.on_connect = None
        self.on_message = None
        self.on_close = None
        self._shutting_down = False
        self.recv_event = threading.Event()

    def __call__(self, url, sslopt, enable_multithread=False):
        self.url = url
        self.sslopt = sslopt
        if 'token' in url:
            token = url.split('token=')[-1]
        else:
            token = None

        self.return_data += [self.on_connect(token)]
        self.recv_event.set()
        return self

    def send(self, data):
        if self.on_message is None:
            return

        return_data = self.on_message(json.loads(data))

        if return_data:
            self.return_data += [return_data]
            self.recv_event.set()

    def recv(self):
        self.recv_event.wait()
        if self._shutting_down:
            return ''

        self.recv_event.clear()
        response = json.dumps(self.return_data.pop(0))
        return response

    def close(self):
        self._shutting_down = True
        self.recv_event.set()
        self.on_close()


class WebSocketTest(unittest.TestCase):
    remote = None
    client = None
    applications = []
    config = None
    ssdp_thread = None
    ssdp_event = None
    ssdp_sock = None
    func = None
    result = None

    NO_CONNECTION = 'no connection'
    PREVIOUS_TEST_FAILED = 'previous test failed'
    TIMED_OUT = 'timed out'
    APPLICATIONS_FAILED = 'no applications received'
    GET_APPLICATION_FAILED = 'get application failed'
    GET_CATEGORY_FAILED = 'get category failed'
    GET_CONTENT_FAILED = 'get content failed'

    @staticmethod
    def _unserialize_string(s):
        return base64.b64decode(s).encode("utf-8")

    @staticmethod
    def _serialize_string(s):

        if not isinstance(s, bytes):
            s = s.encode()
        return base64.b64encode(s).decode("utf-8")

    def test_001_CONNECTION(self):
        # sys.modules['samsungctl.application']._instances.clear()

        self.upnp_app = flask.Flask('Encrypted XML Provider')
        self.api_app = flask.Flask('API Provider')

        def get_node(xml, xmlns, tag):
            tag = '{{{xmlns}}}{tag}'.format(
                xmlns=xmlns,
                tag=tag
            )
            return xml.find(tag)

        def get_func():
            try:
                envelope = etree.fromstring(flask.request.data)
            except etree.ParseError:
                self.fail('XML_PARSE_ERROR')

            if envelope is None:
                self.fail('NO_ENVELOPE:\n' + flask.request.data)

            body = get_node(envelope, ENVELOPE_XMLNS, 'Body')
            if body is None:
                self.fail('NO_BODY')

            for func in body:
                if func.tag == WebSocketTest.func:
                    break
            else:
                self.fail('NO_FUNC: ' + WebSocketTest.func)

            envelope = strip_xmlns(envelope)
            body = envelope.find('Body')

            for func in body:
                if func.tag == WebSocketTest.func:
                    return func

        def get_file(path):
            path = os.path.join(BASE_PATH, 'upnp', 'encrypted_upnp', path)
            with open(path, 'r') as f:
                return f.read()

        def get_service_func(path):
            service_xml = etree.fromstring(get_file(path))
            service_xml = strip_xmlns(service_xml)
            action_list = service_xml.find('actionList')

            value_table = service_xml.find('serviceStateTable')

            for action in action_list:
                name = action.find('name')
                if name.text == self.func:
                    return action, value_table

        def check_value(func, action, value_table):
            arguments = action.find('argumentList')

            for argument in arguments:
                direction = argument.find('direction')
                if direction.text != 'in':
                    continue
                name = argument.find('name')
                param = func.find(name.text)
                if param is None:
                    self.fail('NO_PARAM: ' + name.text)

                value = param.text
                variable_name = argument.find('relatedStateVariable').text

                for variable in value_table:
                    name = variable.find('name')

                    if name.text != variable_name:
                        continue

                    data_type = variable.find('dataType').text
                    data_type = data_type_classes[data_type]

                    allowed_values = variable.find('allowedValueList')
                    allowed_value_range = variable.find('allowedValueRange')

                    value = data_type(value)

                    if allowed_values is not None:
                        allowed_values = list(av.text for av in allowed_values)
                        if value not in allowed_values:
                            self.fail('VALUE_NOT_ALLOWED')
                    elif allowed_value_range is not None:
                        min = allowed_value_range.find('min')
                        max = allowed_value_range.find('max')
                        step = allowed_value_range.find('step')
                        if min is not None and data_type(min.text) > value:
                            self.fail('VALUE_LOWER_THEN_MIN')

                        if max is not None and data_type(max.text) < value:
                            self.fail('VALUE_GREATER_THEN_MAX')

                        if step is not None and value % data_type(step.text):
                            self.fail('VALUE_INCREMENT_INCORRECT')
                    break

        def shutdown_server():
            func = flask.request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()

        @self.upnp_app.route('/shutdown', methods=['POST'])
        def shutdown():
            shutdown_server()
            return 'Server shutting down...'

        @self.api_app.route('/shutdown', methods=['POST'])
        def shutdown():
            shutdown_server()
            return 'Server shutting down...'

        @self.api_app.route('/api/v2/')
        def api_v2():
            res = dict(
                device=dict(
                    FrameTVSupport=False,
                    GamePadSupport=True,
                    ImeSyncedSupport=True,
                    OS="Tizen",
                    VoiceSupport=True,
                    countryCode="IT",
                    description="Samsung DTV RCR",
                    developerIP="192.168.2.180",
                    developerMode="1",
                    duid="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    firmwareVersion="Unknown",
                    id="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    ip="192.168.2.100",
                    model="18_KANTM2_QTV",
                    modelName="QE55Q6FNA",
                    name="[TV] Samsung Q6 Series (55)",
                    networkType="wired",
                    resolution="3840x2160",
                    smartHubAgreement=True,
                    type="Samsung SmartTV",
                    udn="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    wifiMac="70:2a:d5:8f:5a:0d",
                    isSupport=json.dumps(
                        dict(
                            DMP_DRM_PLAYREADY=False,
                            DMP_DRM_WIDEVINE=False,
                            DMP_available=True,
                            EDEN_available=True,
                            FrameTVSupport=False,
                            ImeSyncedSupport=True,
                            TokenAuthSupport=True,
                            remote_available=True,
                            remote_fourDirections=True,
                            remote_touchPad=True,
                            remote_voiceControl=True
                        )
                    ),
                    remote="1.0",
                    uri="http://192.168.2.100:8001/api/v2/",
                    version="2.0.25"
                )
            )

            return json.dumps(res)

        @self.upnp_app.route('/smp_3_')
        def smp_3_():
            return get_file('smp_2_/smp_3_.xml')

        @self.upnp_app.route('/smp_8_')
        def smp_8_():
            return get_file('smp_7_/smp_8_.xml')

        @self.upnp_app.route('/smp_16_')
        def smp_16_():
            return get_file('smp_15_/smp_16_.xml')

        @self.upnp_app.route('/smp_19_')
        def smp_19_():
            return get_file('smp_15_/smp_19_.xml')

        @self.upnp_app.route('/smp_22_')
        def smp_22_():
            return get_file('smp_15_/smp_22_.xml')

        @self.upnp_app.route('/smp_26_')
        def smp_26_():
            return get_file('smp_25_/smp_26_.xml')

        @self.upnp_app.route('/smp_4_', methods=['POST'])
        def smp_4_():
            func = get_func()
            action, value_table = get_service_func('smp_2_/smp_3_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_9_', methods=['POST'])
        def smp_9_():
            func = get_func()
            action, value_table = get_service_func('smp_7_/smp_8_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_17_', methods=['POST'])
        def smp_17_():
            func = get_func()
            action, value_table = get_service_func('smp_15_/smp_16_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_20_', methods=['POST'])
        def smp_20_():
            func = get_func()
            action, value_table = get_service_func('smp_15_/smp_19_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_23_', methods=['POST'])
        def smp_23_():
            func = get_func()
            action, value_table = get_service_func('smp_15_/smp_22_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_27_', methods=['POST'])
        def smp_27_():
            func = get_func()
            action, value_table = get_service_func('smp_25_/smp_26_.xml')
            check_value(func, action, value_table)
            return WebSocketTest.result

        @self.upnp_app.route('/smp_2_')
        def smp_2_():
            return get_file('smp_2_.xml')

        @self.upnp_app.route('/smp_7_')
        def smp_7_():
            return get_file('smp_7_.xml')

        @self.upnp_app.route('/smp_15_')
        def smp_15_():
            return get_file('smp_15_.xml')

        @self.upnp_app.route('/smp_25_')
        def smp_25_():
            return get_file('smp_25_.xml')

        self.ssdp_event = WebSocketTest.ssdp_event = threading.Event()
        self.ssdp_sock = ssdp_sock = WebSocketTest.ssdp_sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )
        self.ssdp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ssdp_sock.bind(BIND_ADDREESS)
        group = socket.inet_aton(IPV4_MCAST_GRP)
        group_membership = struct.pack('4sL', group, socket.INADDR_ANY)
        ssdp_sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            group_membership
        )

        def ssdp_do():
            while not self.ssdp_event.isSet():
                try:
                    data, address = self.ssdp_sock.recvfrom(1024)
                except socket.error:
                    break

                if not data:
                    continue

                packet = convert_packet(data)

                if packet['TYPE'] != 'M-SEARCH':
                    continue

                if (
                    'MAN' in packet and
                    'ST' in packet and
                    packet['MAN'] == '"ssdp:discover"' and
                    packet['ST'] in ('ssdp:all', 'upnp:rootdevice')
                ):
                    for ssdp_packet in ssdp.ENCRYPTED_PACKETS:
                        self.ssdp_sock.sendto(
                            ssdp_packet.format(
                                ip=LOCAL_IP,
                                port=UPNP_PORT
                            ).encode('utf-8'),
                            address
                        )

        def upnp_do():
            self.upnp_app.run(host='0.0.0.0', port=UPNP_PORT)

        def api_do():
            self.api_app.run(host='0.0.0.0', port=8001)

        self.upnp_thread = threading.Thread(target=upnp_do, name='upnp_server')
        self.upnp_thread.start()

        self.api_thread = threading.Thread(target=api_do, name='api_server')
        self.api_thread.start()

        self.ssdp_thread = WebSocketTest.ssdp_thread = threading.Thread(
            target=ssdp_do,
            name='ssdp_listen'
        )
        self.ssdp_thread.start()
        #
        # for config in samsungctl.discover():
        #     print(str(list(config)))

        WebSocketTest.config = samsungctl.Config(
            name="samsungctl",
            description="PC",
            id="",
            method="websocket",
            host='127.0.0.1',
            port=8001,
            timeout=0,
            upnp_locations=[]
        )

        self.config.log_level = LOG_LEVEL

        self.connection_event = threading.Event()
        WebSocketTest.client = FakeWebsocketClient(self)

        remote_websocket = sys.modules['samsungctl.remote_websocket']
        remote_websocket.websocket.create_connection = self.client

        self.client.on_connect = self.on_connect
        self.client.on_close = self.on_disconnect

        logger.info('connection test')
        logger.info(str(self.config))

        try:
            self.remote = WebSocketTest.remote = samsungctl.Remote(self.config)
            self.remote.open()
            self.connection_event.wait(2)
            if not self.connection_event.isSet():
                WebSocketTest.remote = None
                self.fail('connection TIMED_OUT')
            else:
                logger.info('connection successful')
        except:
            WebSocketTest.remote = None
            self.fail('unable to establish connection')

    def test_002_CONNECTION_PARAMS(self):
        if self.remote is None:
            self.skipTest('NO_CONNECTION')

        url = URL_FORMAT.format(
            self.config.host,
            self.config.port,
            self._serialize_string(self.config.name)
        )

        self.assertEqual(url, self.client.url)

    def test_003_GET_VOLUME(self):
        WebSocketTest.func = 'GetVolume'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            [['CurrentVolume', 50]]
        )
        self.assertEqual(50, self.remote.volume, 'VOLUME_NOT_50')

    def test_003_SET_VOLUME(self):
        WebSocketTest.func = 'SetVolume'
        WebSocketTest.result = build_xml_response(self.func + 'Response', [])
        self.remote.volume = 30

    def test_004_GET_MUTE(self):
        WebSocketTest.func = 'GetMute'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            [['CurrentMute', '1']]
        )
        self.assertEqual(True, self.remote.mute, 'MUTE_NOT_TRUE')

    def test_004_SET_MUTE(self):
        WebSocketTest.func = 'SetMute'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            []
        )
        self.remote.mute = False

    def test_005_GET_BRIGHTNESS(self):
        WebSocketTest.func = 'GetBrightness'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            [['CurrentBrightness', 50]]
        )
        self.assertEqual(50, self.remote.brightness, 'BRIGHTNESS_NOT_50')

    def test_005_SET_BRIGHTNESS(self):
        WebSocketTest.func = 'SetBrightness'
        WebSocketTest.result = build_xml_response(self.func + 'Response', [])
        self.remote.brightness = 50

    def test_006_GET_CONTRAST(self):
        WebSocketTest.func = 'GetContrast'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            [['CurrentContrast', 50]]
        )
        self.assertEqual(50, self.remote.contrast, 'CONTRAST_NOT_50')

    def test_006_SET_CONTRAST(self):
        WebSocketTest.func = 'SetContrast'
        WebSocketTest.result = build_xml_response(self.func + 'Response', [])
        self.remote.contrast = 50

    def test_007_GET_SHARPNESS(self):
        WebSocketTest.func = 'GetSharpness'
        WebSocketTest.result = build_xml_response(
            self.func + 'Response',
            [['CurrentSharpness', 50]]
        )
        self.assertEqual(50, self.remote.sharpness, 'SHARPNESS_NOT_50')

    def test_007_SET_SHARPNESS(self):
        WebSocketTest.func = 'SetSharpness'
        WebSocketTest.result = build_xml_response(self.func + 'Response', [])
        self.remote.sharpness = 50

    # @key_wrapper
    def test_0100_KEY_POWEROFF(self):
        """Power OFF key test"""
        pass

    # @key_wrapper
    def test_0101_KEY_POWERON(self):
        """Power On key test"""
        pass

    # @key_wrapper
    def test_0102_KEY_POWER(self):
        """Power Toggle key test"""
        pass

    @key_wrapper
    def test_0103_KEY_SOURCE(self):
        """Source key test"""
        pass

    @key_wrapper
    def test_0104_KEY_COMPONENT1(self):
        """Component 1 key test"""
        pass

    @key_wrapper
    def test_0105_KEY_COMPONENT2(self):
        """Component 2 key test"""
        pass

    @key_wrapper
    def test_0106_KEY_AV1(self):
        """AV 1 key test"""
        pass

    @key_wrapper
    def test_0107_KEY_AV2(self):
        """AV 2 key test"""
        pass

    @key_wrapper
    def test_0108_KEY_AV3(self):
        """AV 3 key test"""
        pass

    @key_wrapper
    def test_0109_KEY_SVIDEO1(self):
        """S Video 1 key test"""
        pass

    @key_wrapper
    def test_0110_KEY_SVIDEO2(self):
        """S Video 2 key test"""
        pass

    @key_wrapper
    def test_0111_KEY_SVIDEO3(self):
        """S Video 3 key test"""
        pass

    @key_wrapper
    def test_0112_KEY_HDMI(self):
        """HDMI key test"""
        pass

    @key_wrapper
    def test_0113_KEY_HDMI1(self):
        """HDMI 1 key test"""
        pass

    @key_wrapper
    def test_0114_KEY_HDMI2(self):
        """HDMI 2 key test"""
        pass

    @key_wrapper
    def test_0115_KEY_HDMI3(self):
        """HDMI 3 key test"""
        pass

    @key_wrapper
    def test_0116_KEY_HDMI4(self):
        """HDMI 4 key test"""
        pass

    @key_wrapper
    def test_0117_KEY_FM_RADIO(self):
        """FM Radio key test"""
        pass

    @key_wrapper
    def test_0118_KEY_DVI(self):
        """DVI key test"""
        pass

    @key_wrapper
    def test_0119_KEY_DVR(self):
        """DVR key test"""
        pass

    @key_wrapper
    def test_0120_KEY_TV(self):
        """TV key test"""
        pass

    @key_wrapper
    def test_0121_KEY_ANTENA(self):
        """Analog TV key test"""
        pass

    @key_wrapper
    def test_0122_KEY_DTV(self):
        """Digital TV key test"""
        pass

    @key_wrapper
    def test_0123_KEY_1(self):
        """Key1 key test"""
        pass

    @key_wrapper
    def test_0124_KEY_2(self):
        """Key2 key test"""
        pass

    @key_wrapper
    def test_0125_KEY_3(self):
        """Key3 key test"""
        pass

    @key_wrapper
    def test_0126_KEY_4(self):
        """Key4 key test"""
        pass

    @key_wrapper
    def test_0127_KEY_5(self):
        """Key5 key test"""
        pass

    @key_wrapper
    def test_0128_KEY_6(self):
        """Key6 key test"""
        pass

    @key_wrapper
    def test_0129_KEY_7(self):
        """Key7 key test"""
        pass

    @key_wrapper
    def test_0130_KEY_8(self):
        """Key8 key test"""
        pass

    @key_wrapper
    def test_0131_KEY_9(self):
        """Key9 key test"""
        pass

    @key_wrapper
    def test_0132_KEY_0(self):
        """Key0 key test"""
        pass

    @key_wrapper
    def test_0133_KEY_PANNEL_CHDOWN(self):
        """3D key test"""
        pass

    @key_wrapper
    def test_0134_KEY_ANYNET(self):
        """AnyNet+ key test"""
        pass

    @key_wrapper
    def test_0135_KEY_ESAVING(self):
        """Energy Saving key test"""
        pass

    @key_wrapper
    def test_0136_KEY_SLEEP(self):
        """Sleep Timer key test"""
        pass

    @key_wrapper
    def test_0137_KEY_DTV_SIGNAL(self):
        """DTV Signal key test"""
        pass

    @key_wrapper
    def test_0138_KEY_CHUP(self):
        """Channel Up key test"""
        pass

    @key_wrapper
    def test_0139_KEY_CHDOWN(self):
        """Channel Down key test"""
        pass

    @key_wrapper
    def test_0140_KEY_PRECH(self):
        """Previous Channel key test"""
        pass

    @key_wrapper
    def test_0141_KEY_FAVCH(self):
        """Favorite Channels key test"""
        pass

    @key_wrapper
    def test_0142_KEY_CH_LIST(self):
        """Channel List key test"""
        pass

    @key_wrapper
    def test_0143_KEY_AUTO_PROGRAM(self):
        """Auto Program key test"""
        pass

    @key_wrapper
    def test_0144_KEY_MAGIC_CHANNEL(self):
        """Magic Channel key test"""
        pass

    @key_wrapper
    def test_0145_KEY_VOLUP(self):
        """Volume Up key test"""
        pass

    @key_wrapper
    def test_0146_KEY_VOLDOWN(self):
        """Volume Down key test"""
        pass

    @key_wrapper
    def test_0147_KEY_MUTE(self):
        """Mute key test"""
        pass

    @key_wrapper
    def test_0148_KEY_UP(self):
        """Navigation Up key test"""
        pass

    @key_wrapper
    def test_0149_KEY_DOWN(self):
        """Navigation Down key test"""
        pass

    @key_wrapper
    def test_0150_KEY_LEFT(self):
        """Navigation Left key test"""
        pass

    @key_wrapper
    def test_0151_KEY_RIGHT(self):
        """Navigation Right key test"""
        pass

    @key_wrapper
    def test_0152_KEY_RETURN(self):
        """Navigation Return/Back key test"""
        pass

    @key_wrapper
    def test_0153_KEY_ENTER(self):
        """Navigation Enter key test"""
        pass

    @key_wrapper
    def test_0154_KEY_REWIND(self):
        """Rewind key test"""
        pass

    @key_wrapper
    def test_0155_KEY_STOP(self):
        """Stop key test"""
        pass

    @key_wrapper
    def test_0156_KEY_PLAY(self):
        """Play key test"""
        pass

    @key_wrapper
    def test_0157_KEY_FF(self):
        """Fast Forward key test"""
        pass

    @key_wrapper
    def test_0158_KEY_REC(self):
        """Record key test"""
        pass

    @key_wrapper
    def test_0159_KEY_PAUSE(self):
        """Pause key test"""
        pass

    @key_wrapper
    def test_0160_KEY_LIVE(self):
        """Live key test"""
        pass

    @key_wrapper
    def test_0161_KEY_QUICK_REPLAY(self):
        """fnKEY_QUICK_REPLAY key test"""
        pass

    @key_wrapper
    def test_0162_KEY_STILL_PICTURE(self):
        """fnKEY_STILL_PICTURE key test"""
        pass

    @key_wrapper
    def test_0163_KEY_INSTANT_REPLAY(self):
        """fnKEY_INSTANT_REPLAY key test"""
        pass

    @key_wrapper
    def test_0164_KEY_PIP_ONOFF(self):
        """PIP On/Off key test"""
        pass

    @key_wrapper
    def test_0165_KEY_PIP_SWAP(self):
        """PIP Swap key test"""
        pass

    @key_wrapper
    def test_0166_KEY_PIP_SIZE(self):
        """PIP Size key test"""
        pass

    @key_wrapper
    def test_0167_KEY_PIP_CHUP(self):
        """PIP Channel Up key test"""
        pass

    @key_wrapper
    def test_0168_KEY_PIP_CHDOWN(self):
        """PIP Channel Down key test"""
        pass

    @key_wrapper
    def test_0169_KEY_AUTO_ARC_PIP_SMALL(self):
        """PIP Small key test"""
        pass

    @key_wrapper
    def test_0170_KEY_AUTO_ARC_PIP_WIDE(self):
        """PIP Wide key test"""
        pass

    @key_wrapper
    def test_0171_KEY_AUTO_ARC_PIP_RIGHT_BOTTOM(self):
        """PIP Bottom Right key test"""
        pass

    @key_wrapper
    def test_0172_KEY_AUTO_ARC_PIP_SOURCE_CHANGE(self):
        """PIP Source Change key test"""
        pass

    @key_wrapper
    def test_0173_KEY_PIP_SCAN(self):
        """PIP Scan key test"""
        pass

    @key_wrapper
    def test_0174_KEY_VCR_MODE(self):
        """VCR Mode key test"""
        pass

    @key_wrapper
    def test_0175_KEY_CATV_MODE(self):
        """CATV Mode key test"""
        pass

    @key_wrapper
    def test_0176_KEY_DSS_MODE(self):
        """DSS Mode key test"""
        pass

    @key_wrapper
    def test_0177_KEY_TV_MODE(self):
        """TV Mode key test"""
        pass

    @key_wrapper
    def test_0178_KEY_DVD_MODE(self):
        """DVD Mode key test"""
        pass

    @key_wrapper
    def test_0179_KEY_STB_MODE(self):
        """STB Mode key test"""
        pass

    @key_wrapper
    def test_0180_KEY_PCMODE(self):
        """PC Mode key test"""
        pass

    @key_wrapper
    def test_0181_KEY_GREEN(self):
        """Green key test"""
        pass

    @key_wrapper
    def test_0182_KEY_YELLOW(self):
        """Yellow key test"""
        pass

    @key_wrapper
    def test_0183_KEY_CYAN(self):
        """Cyan key test"""
        pass

    @key_wrapper
    def test_0184_KEY_RED(self):
        """Red key test"""
        pass

    @key_wrapper
    def test_0185_KEY_TTX_MIX(self):
        """Teletext Mix key test"""
        pass

    @key_wrapper
    def test_0186_KEY_TTX_SUBFACE(self):
        """Teletext Subface key test"""
        pass

    @key_wrapper
    def test_0187_KEY_ASPECT(self):
        """Aspect Ratio key test"""
        pass

    @key_wrapper
    def test_0188_KEY_PICTURE_SIZE(self):
        """Picture Size key test"""
        pass

    @key_wrapper
    def test_0189_KEY_4_3(self):
        """Aspect Ratio 4:3 key test"""
        pass

    @key_wrapper
    def test_0190_KEY_16_9(self):
        """Aspect Ratio 16:9 key test"""
        pass

    @key_wrapper
    def test_0191_KEY_EXT14(self):
        """Aspect Ratio 3:4 (Alt) key test"""
        pass

    @key_wrapper
    def test_0192_KEY_EXT15(self):
        """Aspect Ratio 16:9 (Alt) key test"""
        pass

    @key_wrapper
    def test_0193_KEY_PMODE(self):
        """Picture Mode key test"""
        pass

    @key_wrapper
    def test_0194_KEY_PANORAMA(self):
        """Picture Mode Panorama key test"""
        pass

    @key_wrapper
    def test_0195_KEY_DYNAMIC(self):
        """Picture Mode Dynamic key test"""
        pass

    @key_wrapper
    def test_0196_KEY_STANDARD(self):
        """Picture Mode Standard key test"""
        pass

    @key_wrapper
    def test_0197_KEY_MOVIE1(self):
        """Picture Mode Movie key test"""
        pass

    @key_wrapper
    def test_0198_KEY_GAME(self):
        """Picture Mode Game key test"""
        pass

    @key_wrapper
    def test_0199_KEY_CUSTOM(self):
        """Picture Mode Custom key test"""
        pass

    @key_wrapper
    def test_0200_KEY_EXT9(self):
        """Picture Mode Movie (Alt) key test"""
        pass

    @key_wrapper
    def test_0201_KEY_EXT10(self):
        """Picture Mode Standard (Alt) key test"""
        pass

    @key_wrapper
    def test_0202_KEY_MENU(self):
        """Menu key test"""
        pass

    @key_wrapper
    def test_0203_KEY_TOPMENU(self):
        """Top Menu key test"""
        pass

    @key_wrapper
    def test_0204_KEY_TOOLS(self):
        """Tools key test"""
        pass

    @key_wrapper
    def test_0205_KEY_HOME(self):
        """Home key test"""
        pass

    @key_wrapper
    def test_0206_KEY_CONTENTS(self):
        """Contents key test"""
        pass

    @key_wrapper
    def test_0207_KEY_GUIDE(self):
        """Guide key test"""
        pass

    @key_wrapper
    def test_0208_KEY_DISC_MENU(self):
        """Disc Menu key test"""
        pass

    @key_wrapper
    def test_0209_KEY_DVR_MENU(self):
        """DVR Menu key test"""
        pass

    @key_wrapper
    def test_0210_KEY_HELP(self):
        """Help key test"""
        pass

    @key_wrapper
    def test_0211_KEY_INFO(self):
        """Info key test"""
        pass

    @key_wrapper
    def test_0212_KEY_CAPTION(self):
        """Caption key test"""
        pass

    @key_wrapper
    def test_0213_KEY_CLOCK_DISPLAY(self):
        """ClockDisplay key test"""
        pass

    @key_wrapper
    def test_0214_KEY_SETUP_CLOCK_TIMER(self):
        """Setup Clock key test"""
        pass

    @key_wrapper
    def test_0215_KEY_SUB_TITLE(self):
        """Subtitle key test"""
        pass

    @key_wrapper
    def test_0216_KEY_ZOOM_MOVE(self):
        """Zoom Move key test"""
        pass

    @key_wrapper
    def test_0217_KEY_ZOOM_IN(self):
        """Zoom In key test"""
        pass

    @key_wrapper
    def test_0218_KEY_ZOOM_OUT(self):
        """Zoom Out key test"""
        pass

    @key_wrapper
    def test_0219_KEY_ZOOM1(self):
        """Zoom 1 key test"""
        pass

    @key_wrapper
    def test_0220_KEY_ZOOM2(self):
        """Zoom 2 key test"""
        pass

    def test_0221_KEY_BT_VOICE_ON(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.remote.control',
                params=dict(
                    Cmd='Press',
                    DataOfCmd='KEY_BT_VOICE',
                    Option="false",
                    TypeOfRemote="SendRemoteKey"
                )
            )

            self.assertEqual(expected_message, message)
            payload = dict(event="ms.voiceApp.standby")
            event.set()
            return payload

        self.client.on_message = on_message
        self.remote.start_voice_recognition()

        event.wait(3)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0222_KEY_BT_VOICE_OFF(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            expected_message = dict(
                method='ms.remote.control',
                params=dict(
                    Cmd='Release',
                    DataOfCmd='KEY_BT_VOICE',
                    Option="false",
                    TypeOfRemote="SendRemoteKey"
                )
            )
            self.assertEqual(expected_message, message)
            payload = dict(event="ms.voiceApp.hide")
            event.set()
            return payload

        event = threading.Event()
        self.client.on_message = on_message
        self.remote.stop_voice_recognition()

        event.wait(3)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0300_EDEN_APP_GET(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE

            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        WebSocketTest.applications = self.remote.applications[:]
        self.client.on_message = None

        if not self.applications:
            self.fail('APPLICATIONS_FAILED')

    def test_0301_APPLICATION_CATEGORIES_CONTENT(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        if not self.applications:
            self.fail('PREVIOUS_TEST_FAILED')

        for app in self.applications:
            logger.info(app.name)

            for category in app:
                logger.info('    ' + repr(category.title))

                for content in category:
                    logger.info('        ' + repr(content.title))

    def test_0303_GET_APPLICATION(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

    def test_0304_LAUNCH_APPLICATION(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.channel.emit',
                params=dict(
                    event='ed.apps.launch',
                    to='host',
                    data=dict(
                        appId='11101200001',
                        action_type='DEEP_LINK'
                    )
                )
            )
            self.assertEqual(expected_message, message)
            event.set()

        self.client.on_message = on_message
        app.run()
        self.client.on_message = None

        event.wait(15.0)
        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0305_GET_CONTENT_CATEGORY(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

    def test_0306_GET_CONTENT(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )

            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

        content = category.get_content('How the Grinch Stole Christmas')
        if content is None:
            self.fail('GET_CONTENT_FAILED')

    def test_0307_PLAY_CONTENT(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

        content = category.get_content('How the Grinch Stole Christmas')
        if content is None:
            self.fail('GET_CONTENT_FAILED')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.channel.emit',
                params=dict(
                    event='ed.apps.launch',
                    to='host',
                    data=dict(
                        appId='11101200001',
                        action_type='DEEP_LINK',
                        metaTag=(
                            'm=60000901&trackId=254080000&&source_type_payload'
                            '=groupIndex%3D2%26tileIndex%3D6%26action%3Dmdp%26'
                            'movieId%3D60000901%26trackId%3D254080000'
                        )
                    )
                )
            )

            self.assertEqual(expected_message, message)
            event.set()

        self.client.on_message = on_message
        content.run()
        event.wait(15.0)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_999_DISCONNECT(self):
        if self.remote is not None:
            self.remote.close()

        import requests

        self.ssdp_event.set()
        self.ssdp_sock.shutdown(socket.SHUT_RDWR)
        self.ssdp_sock.close()
        self.ssdp_thread.join(3.0)

        requests.post('http://127.0.0.1:8001/shutdown')
        requests.post('http://127.0.0.1:{0}/shutdown'.format(UPNP_PORT))

    def on_disconnect(self):
        pass

    def on_connect(self, _):
        guid = str(uuid.uuid4())[1:-1]
        name = self._serialize_string(self.config.name)

        clients = dict(
            attributes=dict(name=name),
            connectTime=time.time(),
            deviceName=name,
            id=guid,
            isHost=False
        )

        data = dict(clients=[clients], id=guid)
        payload = dict(data=data, event='ms.channel.connect')
        self.connection_event.set()
        return payload


class WebSocketSSLTest(unittest.TestCase):
    remote = None
    client = None
    token = None
    applications = []
    config = None

    NO_CONNECTION = 'no connection'
    PREVIOUS_TEST_FAILED = 'previous test failed'
    TIMED_OUT = 'timed out'
    APPLICATIONS_FAILED = 'no applications received'
    GET_APPLICATION_FAILED = 'get application failed'
    GET_CATEGORY_FAILED = 'get category failed'
    GET_CONTENT_FAILED = 'get content failed'

    @staticmethod
    def _unserialize_string(s):
        return base64.b64decode(s).encode("utf-8")

    @staticmethod
    def _serialize_string(s):
        if not isinstance(s, bytes):
            s = s.encode()
        return base64.b64encode(s).decode("utf-8")

    def test_001_CONNECTION(self):

        self.app = flask.Flask('Power Provider')

        def shutdown_server():
            func = flask.request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()

        @self.app.route('/shutdown', methods=['POST'])
        def shutdown():
            shutdown_server()
            return 'Server shutting down...'

        @self.app.route('/api/v2/')
        def api_v2():
            res = dict(
                device=dict(
                    FrameTVSupport=False,
                    GamePadSupport=True,
                    ImeSyncedSupport=True,
                    OS="Tizen",
                    TokenAuthSupport=True,
                    VoiceSupport=True,
                    countryCode="IT",
                    description="Samsung DTV RCR",
                    developerIP="192.168.2.180",
                    developerMode="1",
                    duid="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    firmwareVersion="Unknown",
                    id="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    ip="192.168.2.100",
                    model="18_KANTM2_QTV",
                    modelName="QE55Q6FNA",
                    name="[TV] Samsung Q6 Series (55)",
                    networkType="wired",
                    resolution="3840x2160",
                    smartHubAgreement=True,
                    type="Samsung SmartTV",
                    udn="uuid:df830908-990a-4710-b2c0-5d18c1522f4e",
                    wifiMac="70:2a:d5:8f:5a:0d",
                    isSupport=json.dumps(
                        dict(
                            DMP_DRM_PLAYREADY=False,
                            DMP_DRM_WIDEVINE=False,
                            DMP_available=True,
                            EDEN_available=True,
                            FrameTVSupport=False,
                            ImeSyncedSupport=True,
                            TokenAuthSupport=True,
                            remote_available=True,
                            remote_fourDirections=True,
                            remote_touchPad=True,
                            remote_voiceControl=True
                        )
                    ),
                    remote="1.0",
                    uri="http://192.168.2.100:8001/api/v2/",
                    version="2.0.25"
                )
            )

            return json.dumps(res)

        def do():
            self.app.run(host='0.0.0.0', port=8001)

        threading.Thread(target=do).start()

        # sys.modules['samsungctl.application']._instances.clear()
        WebSocketSSLTest.config = samsungctl.Config(
            name="samsungctl",
            description="PC",
            id="",
            method="websocket",
            host='127.0.0.1',
            port=8002,
            timeout=0
        )
        self.config.log_level = LOG_LEVEL
        self.connection_event = threading.Event()
        WebSocketSSLTest.client = FakeWebsocketClient(self)

        remote_websocket = sys.modules['samsungctl.remote_websocket']
        remote_websocket.websocket.create_connection = self.client

        self.client.on_connect = self.on_connect
        self.client.on_close = self.on_disconnect

        logger.info('connection test')
        logger.info(str(self.config))

        try:
            self.remote = WebSocketSSLTest.remote = (
                samsungctl.Remote(self.config)
            )
            self.remote.open()
            self.connection_event.wait(2)
            if not self.connection_event.isSet():
                WebSocketSSLTest.remote = None
                self.fail('connection TIMED_OUT')
            else:
                logger.info('connection successful')
        except:
            import traceback
            traceback.print_exc()
            WebSocketSSLTest.remote = None
            self.fail('unable to establish connection')

    def test_002_CONNECTION_PARAMS(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        url = SSL_URL_FORMAT.format(
            self.config.host,
            self.config.port,
            self._serialize_string(self.config.name)
        )

        sslopt = {"cert_reqs": ssl.CERT_NONE}
        if 'token' in self.client.url:
            url += '&token=' + self.token

        self.assertEqual(url, self.client.url)
        self.assertEqual(sslopt, self.client.sslopt)

    # @key_wrapper
    def test_0100_KEY_POWEROFF(self):
        """Power OFF key test"""
        pass

    # @key_wrapper
    def test_0101_KEY_POWERON(self):
        """Power On key test"""
        pass

    # @key_wrapper
    def test_0102_KEY_POWER(self):
        """Power Toggle key test"""
        pass

    @key_wrapper
    def test_0103_KEY_SOURCE(self):
        """Source key test"""
        pass

    @key_wrapper
    def test_0104_KEY_COMPONENT1(self):
        """Component 1 key test"""
        pass

    @key_wrapper
    def test_0105_KEY_COMPONENT2(self):
        """Component 2 key test"""
        pass

    @key_wrapper
    def test_0106_KEY_AV1(self):
        """AV 1 key test"""
        pass

    @key_wrapper
    def test_0107_KEY_AV2(self):
        """AV 2 key test"""
        pass

    @key_wrapper
    def test_0108_KEY_AV3(self):
        """AV 3 key test"""
        pass

    @key_wrapper
    def test_0109_KEY_SVIDEO1(self):
        """S Video 1 key test"""
        pass

    @key_wrapper
    def test_0110_KEY_SVIDEO2(self):
        """S Video 2 key test"""
        pass

    @key_wrapper
    def test_0111_KEY_SVIDEO3(self):
        """S Video 3 key test"""
        pass

    @key_wrapper
    def test_0112_KEY_HDMI(self):
        """HDMI key test"""
        pass

    @key_wrapper
    def test_0113_KEY_HDMI1(self):
        """HDMI 1 key test"""
        pass

    @key_wrapper
    def test_0114_KEY_HDMI2(self):
        """HDMI 2 key test"""
        pass

    @key_wrapper
    def test_0115_KEY_HDMI3(self):
        """HDMI 3 key test"""
        pass

    @key_wrapper
    def test_0116_KEY_HDMI4(self):
        """HDMI 4 key test"""
        pass

    @key_wrapper
    def test_0117_KEY_FM_RADIO(self):
        """FM Radio key test"""
        pass

    @key_wrapper
    def test_0118_KEY_DVI(self):
        """DVI key test"""
        pass

    @key_wrapper
    def test_0119_KEY_DVR(self):
        """DVR key test"""
        pass

    @key_wrapper
    def test_0120_KEY_TV(self):
        """TV key test"""
        pass

    @key_wrapper
    def test_0121_KEY_ANTENA(self):
        """Analog TV key test"""
        pass

    @key_wrapper
    def test_0122_KEY_DTV(self):
        """Digital TV key test"""
        pass

    @key_wrapper
    def test_0123_KEY_1(self):
        """Key1 key test"""
        pass

    @key_wrapper
    def test_0124_KEY_2(self):
        """Key2 key test"""
        pass

    @key_wrapper
    def test_0125_KEY_3(self):
        """Key3 key test"""
        pass

    @key_wrapper
    def test_0126_KEY_4(self):
        """Key4 key test"""
        pass

    @key_wrapper
    def test_0127_KEY_5(self):
        """Key5 key test"""
        pass

    @key_wrapper
    def test_0128_KEY_6(self):
        """Key6 key test"""
        pass

    @key_wrapper
    def test_0129_KEY_7(self):
        """Key7 key test"""
        pass

    @key_wrapper
    def test_0130_KEY_8(self):
        """Key8 key test"""
        pass

    @key_wrapper
    def test_0131_KEY_9(self):
        """Key9 key test"""
        pass

    @key_wrapper
    def test_0132_KEY_0(self):
        """Key0 key test"""
        pass

    @key_wrapper
    def test_0133_KEY_PANNEL_CHDOWN(self):
        """3D key test"""
        pass

    @key_wrapper
    def test_0134_KEY_ANYNET(self):
        """AnyNet+ key test"""
        pass

    @key_wrapper
    def test_0135_KEY_ESAVING(self):
        """Energy Saving key test"""
        pass

    @key_wrapper
    def test_0136_KEY_SLEEP(self):
        """Sleep Timer key test"""
        pass

    @key_wrapper
    def test_0137_KEY_DTV_SIGNAL(self):
        """DTV Signal key test"""
        pass

    @key_wrapper
    def test_0138_KEY_CHUP(self):
        """Channel Up key test"""
        pass

    @key_wrapper
    def test_0139_KEY_CHDOWN(self):
        """Channel Down key test"""
        pass

    @key_wrapper
    def test_0140_KEY_PRECH(self):
        """Previous Channel key test"""
        pass

    @key_wrapper
    def test_0141_KEY_FAVCH(self):
        """Favorite Channels key test"""
        pass

    @key_wrapper
    def test_0142_KEY_CH_LIST(self):
        """Channel List key test"""
        pass

    @key_wrapper
    def test_0143_KEY_AUTO_PROGRAM(self):
        """Auto Program key test"""
        pass

    @key_wrapper
    def test_0144_KEY_MAGIC_CHANNEL(self):
        """Magic Channel key test"""
        pass

    @key_wrapper
    def test_0145_KEY_VOLUP(self):
        """Volume Up key test"""
        pass

    @key_wrapper
    def test_0146_KEY_VOLDOWN(self):
        """Volume Down key test"""
        pass

    @key_wrapper
    def test_0147_KEY_MUTE(self):
        """Mute key test"""
        pass

    @key_wrapper
    def test_0148_KEY_UP(self):
        """Navigation Up key test"""
        pass

    @key_wrapper
    def test_0149_KEY_DOWN(self):
        """Navigation Down key test"""
        pass

    @key_wrapper
    def test_0150_KEY_LEFT(self):
        """Navigation Left key test"""
        pass

    @key_wrapper
    def test_0151_KEY_RIGHT(self):
        """Navigation Right key test"""
        pass

    @key_wrapper
    def test_0152_KEY_RETURN(self):
        """Navigation Return/Back key test"""
        pass

    @key_wrapper
    def test_0153_KEY_ENTER(self):
        """Navigation Enter key test"""
        pass

    @key_wrapper
    def test_0154_KEY_REWIND(self):
        """Rewind key test"""
        pass

    @key_wrapper
    def test_0155_KEY_STOP(self):
        """Stop key test"""
        pass

    @key_wrapper
    def test_0156_KEY_PLAY(self):
        """Play key test"""
        pass

    @key_wrapper
    def test_0157_KEY_FF(self):
        """Fast Forward key test"""
        pass

    @key_wrapper
    def test_0158_KEY_REC(self):
        """Record key test"""
        pass

    @key_wrapper
    def test_0159_KEY_PAUSE(self):
        """Pause key test"""
        pass

    @key_wrapper
    def test_0160_KEY_LIVE(self):
        """Live key test"""
        pass

    @key_wrapper
    def test_0161_KEY_QUICK_REPLAY(self):
        """fnKEY_QUICK_REPLAY key test"""
        pass

    @key_wrapper
    def test_0162_KEY_STILL_PICTURE(self):
        """fnKEY_STILL_PICTURE key test"""
        pass

    @key_wrapper
    def test_0163_KEY_INSTANT_REPLAY(self):
        """fnKEY_INSTANT_REPLAY key test"""
        pass

    @key_wrapper
    def test_0164_KEY_PIP_ONOFF(self):
        """PIP On/Off key test"""
        pass

    @key_wrapper
    def test_0165_KEY_PIP_SWAP(self):
        """PIP Swap key test"""
        pass

    @key_wrapper
    def test_0166_KEY_PIP_SIZE(self):
        """PIP Size key test"""
        pass

    @key_wrapper
    def test_0167_KEY_PIP_CHUP(self):
        """PIP Channel Up key test"""
        pass

    @key_wrapper
    def test_0168_KEY_PIP_CHDOWN(self):
        """PIP Channel Down key test"""
        pass

    @key_wrapper
    def test_0169_KEY_AUTO_ARC_PIP_SMALL(self):
        """PIP Small key test"""
        pass

    @key_wrapper
    def test_0170_KEY_AUTO_ARC_PIP_WIDE(self):
        """PIP Wide key test"""
        pass

    @key_wrapper
    def test_0171_KEY_AUTO_ARC_PIP_RIGHT_BOTTOM(self):
        """PIP Bottom Right key test"""
        pass

    @key_wrapper
    def test_0172_KEY_AUTO_ARC_PIP_SOURCE_CHANGE(self):
        """PIP Source Change key test"""
        pass

    @key_wrapper
    def test_0173_KEY_PIP_SCAN(self):
        """PIP Scan key test"""
        pass

    @key_wrapper
    def test_0174_KEY_VCR_MODE(self):
        """VCR Mode key test"""
        pass

    @key_wrapper
    def test_0175_KEY_CATV_MODE(self):
        """CATV Mode key test"""
        pass

    @key_wrapper
    def test_0176_KEY_DSS_MODE(self):
        """DSS Mode key test"""
        pass

    @key_wrapper
    def test_0177_KEY_TV_MODE(self):
        """TV Mode key test"""
        pass

    @key_wrapper
    def test_0178_KEY_DVD_MODE(self):
        """DVD Mode key test"""
        pass

    @key_wrapper
    def test_0179_KEY_STB_MODE(self):
        """STB Mode key test"""
        pass

    @key_wrapper
    def test_0180_KEY_PCMODE(self):
        """PC Mode key test"""
        pass

    @key_wrapper
    def test_0181_KEY_GREEN(self):
        """Green key test"""
        pass

    @key_wrapper
    def test_0182_KEY_YELLOW(self):
        """Yellow key test"""
        pass

    @key_wrapper
    def test_0183_KEY_CYAN(self):
        """Cyan key test"""
        pass

    @key_wrapper
    def test_0184_KEY_RED(self):
        """Red key test"""
        pass

    @key_wrapper
    def test_0185_KEY_TTX_MIX(self):
        """Teletext Mix key test"""
        pass

    @key_wrapper
    def test_0186_KEY_TTX_SUBFACE(self):
        """Teletext Subface key test"""
        pass

    @key_wrapper
    def test_0187_KEY_ASPECT(self):
        """Aspect Ratio key test"""
        pass

    @key_wrapper
    def test_0188_KEY_PICTURE_SIZE(self):
        """Picture Size key test"""
        pass

    @key_wrapper
    def test_0189_KEY_4_3(self):
        """Aspect Ratio 4:3 key test"""
        pass

    @key_wrapper
    def test_0190_KEY_16_9(self):
        """Aspect Ratio 16:9 key test"""
        pass

    @key_wrapper
    def test_0191_KEY_EXT14(self):
        """Aspect Ratio 3:4 (Alt) key test"""
        pass

    @key_wrapper
    def test_0192_KEY_EXT15(self):
        """Aspect Ratio 16:9 (Alt) key test"""
        pass

    @key_wrapper
    def test_0193_KEY_PMODE(self):
        """Picture Mode key test"""
        pass

    @key_wrapper
    def test_0194_KEY_PANORAMA(self):
        """Picture Mode Panorama key test"""
        pass

    @key_wrapper
    def test_0195_KEY_DYNAMIC(self):
        """Picture Mode Dynamic key test"""
        pass

    @key_wrapper
    def test_0196_KEY_STANDARD(self):
        """Picture Mode Standard key test"""
        pass

    @key_wrapper
    def test_0197_KEY_MOVIE1(self):
        """Picture Mode Movie key test"""
        pass

    @key_wrapper
    def test_0198_KEY_GAME(self):
        """Picture Mode Game key test"""
        pass

    @key_wrapper
    def test_0199_KEY_CUSTOM(self):
        """Picture Mode Custom key test"""
        pass

    @key_wrapper
    def test_0200_KEY_EXT9(self):
        """Picture Mode Movie (Alt) key test"""
        pass

    @key_wrapper
    def test_0201_KEY_EXT10(self):
        """Picture Mode Standard (Alt) key test"""
        pass

    @key_wrapper
    def test_0202_KEY_MENU(self):
        """Menu key test"""
        pass

    @key_wrapper
    def test_0203_KEY_TOPMENU(self):
        """Top Menu key test"""
        pass

    @key_wrapper
    def test_0204_KEY_TOOLS(self):
        """Tools key test"""
        pass

    @key_wrapper
    def test_0205_KEY_HOME(self):
        """Home key test"""
        pass

    @key_wrapper
    def test_0206_KEY_CONTENTS(self):
        """Contents key test"""
        pass

    @key_wrapper
    def test_0207_KEY_GUIDE(self):
        """Guide key test"""
        pass

    @key_wrapper
    def test_0208_KEY_DISC_MENU(self):
        """Disc Menu key test"""
        pass

    @key_wrapper
    def test_0209_KEY_DVR_MENU(self):
        """DVR Menu key test"""
        pass

    @key_wrapper
    def test_0210_KEY_HELP(self):
        """Help key test"""
        pass

    @key_wrapper
    def test_0211_KEY_INFO(self):
        """Info key test"""
        pass

    @key_wrapper
    def test_0212_KEY_CAPTION(self):
        """Caption key test"""
        pass

    @key_wrapper
    def test_0213_KEY_CLOCK_DISPLAY(self):
        """ClockDisplay key test"""
        pass

    @key_wrapper
    def test_0214_KEY_SETUP_CLOCK_TIMER(self):
        """Setup Clock key test"""
        pass

    @key_wrapper
    def test_0215_KEY_SUB_TITLE(self):
        """Subtitle key test"""
        pass

    @key_wrapper
    def test_0216_KEY_ZOOM_MOVE(self):
        """Zoom Move key test"""
        pass

    @key_wrapper
    def test_0217_KEY_ZOOM_IN(self):
        """Zoom In key test"""
        pass

    @key_wrapper
    def test_0218_KEY_ZOOM_OUT(self):
        """Zoom Out key test"""
        pass

    @key_wrapper
    def test_0219_KEY_ZOOM1(self):
        """Zoom 1 key test"""
        pass

    @key_wrapper
    def test_0220_KEY_ZOOM2(self):
        """Zoom 2 key test"""
        pass

    def test_0221_KEY_BT_VOICE_ON(self):
        if self.remote is None:
            self.skipTest('NO_CONNECTION')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.remote.control',
                params=dict(
                    Cmd='Press',
                    DataOfCmd='KEY_BT_VOICE',
                    Option="false",
                    TypeOfRemote="SendRemoteKey"
                )
            )

            self.assertEqual(expected_message, message)
            payload = dict(event="ms.voiceApp.standby")
            event.set()
            return payload

        self.client.on_message = on_message
        self.remote.start_voice_recognition()

        event.wait(3)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0222_KEY_BT_VOICE_OFF(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            expected_message = dict(
                method='ms.remote.control',
                params=dict(
                    Cmd='Release',
                    DataOfCmd='KEY_BT_VOICE',
                    Option="false",
                    TypeOfRemote="SendRemoteKey"
                )
            )
            self.assertEqual(expected_message, message)
            payload = dict(event="ms.voiceApp.hide")
            event.set()
            return payload

        event = threading.Event()
        self.client.on_message = on_message
        self.remote.stop_voice_recognition()
        event.wait(3)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0300_EDEN_APP_GET(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE

            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        WebSocketSSLTest.applications = self.remote.applications[:]
        self.client.on_message = None

        if not self.applications:
            self.fail('APPLICATIONS_FAILED')

    def test_0301_APPLICATION_CATEGORIES_CONTENT(self):
        if self.remote is None:
            self.skipTest('NO_CONNECTION')
            return

        if not self.applications:
            self.skipTest('PREVIOUS_TEST_FAILED')
            return

        for app in self.applications:
            logger.info(app.name)

            for category in app:
                logger.info('    ' + repr(category.title))

                for content in category:
                    logger.info('        ' + repr(content.title))

    def test_0303_GET_APPLICATION(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

    def test_0304_LAUNCH_APPLICATION(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.channel.emit',
                params=dict(
                    event='ed.apps.launch',
                    to='host',
                    data=dict(
                        appId='11101200001',
                        action_type='DEEP_LINK'
                    )
                )
            )
            self.assertEqual(expected_message, message)
            event.set()

        self.client.on_message = on_message
        app.run()
        self.client.on_message = None

        event.wait(15.0)
        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_0305_GET_CONTENT_CATEGORY(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

    def test_0306_GET_CONTENT(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )

            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

        content = category.get_content('How the Grinch Stole Christmas')
        if content is None:
            self.fail('GET_CONTENT_FAILED')

    def test_0307_PLAY_CONTENT(self):
        if self.remote is None:
            self.fail('NO_CONNECTION')

        def on_message(message):
            eden_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.edenApp.get',
                    to='host'
                )
            )
            installed_message = dict(
                method='ms.channel.emit',
                params=dict(
                    data='',
                    event='ed.installedApp.get',
                    to='host'
                )
            )

            if message['params']['event'] == 'ed.edenApp.get':
                self.assertEqual(eden_message, message)
                return responses.EDEN_APP_RESPONSE
            elif message['params']['event'] == 'ed.installedApp.get':
                self.assertEqual(installed_message, message)
                return responses.INSTALLED_APP_RESPONSE

        self.client.on_message = on_message
        app = self.remote.get_application('Netflix')
        self.client.on_message = None

        if app is None:
            self.fail('GET_APPLICATION_FAILED')

        category = app.get_category('Trending Now')
        if category is None:
            self.fail('GET_CATEGORY_FAILED')

        content = category.get_content('How the Grinch Stole Christmas')
        if content is None:
            self.fail('GET_CONTENT_FAILED')

        event = threading.Event()

        def on_message(message):
            expected_message = dict(
                method='ms.channel.emit',
                params=dict(
                    event='ed.apps.launch',
                    to='host',
                    data=dict(
                        appId='11101200001',
                        action_type='DEEP_LINK',
                        metaTag=(
                            'm=60000901&trackId=254080000&&source_type_payload'
                            '=groupIndex%3D2%26tileIndex%3D6%26action%3Dmdp%26'
                            'movieId%3D60000901%26trackId%3D254080000'
                        )
                    )
                )
            )

            self.assertEqual(expected_message, message)
            event.set()

        self.client.on_message = on_message
        content.run()
        event.wait(15.0)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_999_DISCONNECT(self):
        if self.remote is not None:
            self.remote.close()

        import requests

        requests.post('http://127.0.0.1:8001/shutdown')

    def on_disconnect(self):
        pass

    def on_connect(self, token):
        guid = str(uuid.uuid4())[1:-1]
        name = self._serialize_string(self.config.name)
        if token is None:
            token = TOKEN

        WebSocketSSLTest.token = token
        clients = dict(
            attributes=dict(name=name, token=token),
            connectTime=time.time(),
            deviceName=name,
            id=guid,
            isHost=False
        )

        data = dict(clients=[clients], id=guid, token=token)
        payload = dict(data=data, event='ms.channel.connect')
        self.connection_event.set()
        return payload


class LegacySocket(object):

    def __init__(self, handler):
        self.handler = handler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 55000))
        self.sock.listen(1)
        self.on_message = None
        self.on_connect = None
        self.on_close = None
        self._event = threading.Event()
        self._thread = threading.Thread(target=self.loop)
        self._thread.start()
        self.conn = None

    def send(self, message):
        # print(repr(message))
        self.conn.sendall(message)

    def loop(self):
        conn, addr = self.sock.accept()
        self.conn = conn
        data = conn.recv(4096)
        self.on_connect(data)

        try:
            while not self._event.isSet():
                data = conn.recv(4096)
                if self.on_message is not None and data:
                    self.on_message(data)
        except socket.error:
            pass

    def close(self):
        self._event.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass
        try:
            self.sock.close()
        except socket.error:
            pass

        self._thread.join(3.0)


def send_key(func):
    key = func.__name__.split('_', 2)[-1]

    def wrapper(self):
        self.send_command(key)

    return wrapper


class LegacyTest(unittest.TestCase):
    remote = None
    client = None
    token = None
    applications = []
    config = None
    func = None
    result = None
    upnp_app = None
    upnp_thread = None
    ssdp_thread = None
    ssdp_event = None
    ssdp_sock = None
    value_check_event = threading.Event()

    NO_CONNECTION = 'no connection'
    TIMED_OUT = 'timed out'

    UPNP_VALUES = {}

    @staticmethod
    def _unserialize_string(s):
        return base64.b64decode(s).encode("utf-8")

    @staticmethod
    def _serialize_string(string, raw=False):
        if isinstance(string, str):
            if sys.version_info[0] > 2:
                string = str.encode(string)

        if not raw:
            string = base64.b64encode(string)

        return bytes([len(string)]) + b"\x00" + string

    def test_001_CONNECTION(self):
        LegacyTest.upnp_app = flask.Flask('Legacy XML Provider')

        def get_node(xml, xmlns, tag):
            tag = '{{{xmlns}}}{tag}'.format(
                xmlns=xmlns,
                tag=tag
            )
            return xml.find(tag)

        def get_func():
            try:
                envelope = etree.fromstring(flask.request.data)
            except etree.ParseError:
                self.fail('XML_PARSE_ERROR')

            if envelope is None:
                self.fail('NO_ENVELOPE:\n' + flask.request.data)

            body = get_node(envelope, ENVELOPE_XMLNS, 'Body')
            if body is None:
                self.fail('NO_BODY')

            for func in body:
                if func.tag == LegacyTest.func:
                    break
            else:
                self.fail('NO_FUNC: ' + LegacyTest.func)

            envelope = strip_xmlns(envelope)
            body = envelope.find('Body')

            for func in body:
                if func.tag == LegacyTest.func:
                    return func

        def get_file(path):
            path = os.path.join(BASE_PATH, 'upnp', 'legacy_upnp', path)
            with open(path, 'r') as f:
                return f.read()

        def get_service_func(path):
            service_xml = etree.fromstring(get_file(path))
            service_xml = strip_xmlns(service_xml)
            action_list = service_xml.find('actionList')

            value_table = service_xml.find('serviceStateTable')

            for action in action_list:
                name = action.find('name')
                if name.text == LegacyTest.func:
                    return action, value_table

        def check_value(func, action, value_table):
            arguments = action.find('argumentList')

            for argument in arguments:
                direction = argument.find('direction')
                if direction.text != 'in':
                    continue
                name = argument.find('name')
                param = func.find(name.text)
                if param is None:
                    self.fail('NO_PARAM: ' + name.text)

                value = param.text
                variable_name = argument.find('relatedStateVariable').text

                for variable in value_table:
                    name = variable.find('name')

                    if name.text != variable_name:
                        continue

                    data_type = variable.find('dataType').text
                    data_type = data_type_classes[data_type]

                    allowed_values = variable.find('allowedValueList')
                    allowed_value_range = variable.find('allowedValueRange')

                    value = data_type(value)

                    if allowed_values is not None:
                        allowed_values = list(av.text for av in allowed_values)
                        if value not in allowed_values:
                            self.fail('VALUE_NOT_ALLOWED')
                    elif allowed_value_range is not None:
                        min = allowed_value_range.find('min')
                        max = allowed_value_range.find('max')
                        step = allowed_value_range.find('step')
                        if min is not None and data_type(min.text) > value:
                            self.fail('VALUE_LOWER_THEN_MIN')

                        if max is not None and data_type(max.text) < value:
                            self.fail('VALUE_GREATER_THEN_MAX')

                        if step is not None and value % data_type(step.text):
                            self.fail('VALUE_INCREMENT_INCORRECT')
                    break
            LegacyTest.value_check_event.set()

        def shutdown_server():
            func = flask.request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()

        @LegacyTest.upnp_app.route('/shutdown', methods=['POST'])
        def shutdown():
            shutdown_server()
            return 'Server shutting down...'

        @LegacyTest.upnp_app.route('/dmr/SamsungMRDesc.xml')
        def samsung_mr_dsc():
            return get_file('dmr/SamsungMRDesc.xml')

        @LegacyTest.upnp_app.route('/dmr/RenderingControl1.xml')
        def rendering_control_1():
            return get_file('dmr/RenderingControl1.xml')

        @LegacyTest.upnp_app.route('/upnp/control/RenderingControl1', methods=['POST'])
        def rendering_control_1_post():
            func = get_func()
            action, value_table = get_service_func('dmr/RenderingControl1.xml')
            check_value(func, action, value_table)
            return LegacyTest.result

        @LegacyTest.upnp_app.route('/dmr/ConnectionManager1.xml')
        def connection_manager_1():
            return get_file('dmr/ConnectionManager1.xml')

        @LegacyTest.upnp_app.route('/upnp/control/ConnectionManager1', methods=['POST'])
        def connection_manager_1_post():
            func = get_func()
            action, value_table = get_service_func('dmr/ConnectionManager1.xml')
            check_value(func, action, value_table)
            return LegacyTest.result

        @LegacyTest.upnp_app.route('/dmr/AVTransport1.xml')
        def av_transport_1():
            return get_file('dmr/AVTransport1.xml')

        @LegacyTest.upnp_app.route('/upnp/control/AVTransport1', methods=['POST'])
        def av_transport_1_post():
            func = get_func()
            action, value_table = get_service_func('dmr/AVTransport1.xml')
            check_value(func, action, value_table)
            return LegacyTest.result

        @LegacyTest.upnp_app.route('/MainTVServer2/MainTVServer2Desc.xml')
        def main_tv_server_desc():
            return get_file('MainTVServer2/MainTVServer2Desc.xml')

        @LegacyTest.upnp_app.route('/MainTVServer2/MainTVAgent2.xml')
        def main_tv_agent_2():
            return get_file('MainTVServer2/MainTVAgent2.xml')

        @LegacyTest.upnp_app.route('/upnp/control/MainTVServer2', methods=['POST'])
        def main_tv_agent_2_post():
            func = get_func()
            action, value_table = get_service_func('MainTVServer2/MainTVAgent2.xml')
            check_value(func, action, value_table)
            return LegacyTest.result

        @LegacyTest.upnp_app.route('/rcr/RemoteControlReceiver.xml')
        def remote_control_receiver():
            return get_file('rcr/RemoteControlReceiver.xml')

        @LegacyTest.upnp_app.route('/rcr/TestRCRService.xml')
        def test_rcr_service():
            return get_file('rcr/TestRCRService.xml')

        @LegacyTest.upnp_app.route('/upnp/control/TestRCRService', methods=['POST'])
        def test_rcr_service_post():
            func = get_func()
            action, value_table = get_service_func('rcr/TestRCRService.xml')
            check_value(func, action, value_table)
            return LegacyTest.result

        LegacyTest.ssdp_event = LegacyTest.ssdp_event = threading.Event()
        LegacyTest.ssdp_sock = ssdp_sock = LegacyTest.ssdp_sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )
        ssdp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ssdp_sock.bind(BIND_ADDREESS)
        group = socket.inet_aton(IPV4_MCAST_GRP)
        group_membership = struct.pack('4sL', group, socket.INADDR_ANY)
        ssdp_sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            group_membership
        )

        def ssdp_do():
            while not LegacyTest.ssdp_event.isSet():
                try:
                    data, address = LegacyTest.ssdp_sock.recvfrom(1024)
                except socket.error:
                    break

                if not data:
                    continue

                packet = convert_packet(data)

                if packet['TYPE'] != 'M-SEARCH':
                    continue

                if (
                    'MAN' in packet and
                    'ST' in packet and
                    packet['MAN'] == '"ssdp:discover"' and
                    packet['ST'] in ('ssdp:all', 'upnp:rootdevice')
                ):
                    for ssdp_packet in ssdp.LEGACY_PACKETS:
                        LegacyTest.ssdp_sock.sendto(
                            ssdp_packet.format(
                                ip=LOCAL_IP,
                                port=UPNP_PORT
                            ).encode('utf-8'),
                            address
                        )

        def upnp_do():
            LegacyTest.upnp_app.run(host='0.0.0.0', port=UPNP_PORT)

        LegacyTest.upnp_thread = threading.Thread(
            target=upnp_do,
            name='upnp_server'
        )
        LegacyTest.upnp_thread.start()

        LegacyTest.ssdp_thread = WebSocketTest.ssdp_thread = threading.Thread(
            target=ssdp_do,
            name='ssdp_listen'
        )
        LegacyTest.ssdp_thread.start()

        LegacyTest.config = samsungctl.Config(
            name="samsungctl",
            description="UnitTest",
            id="123456789",
            method="legacy",
            host='127.0.0.1',
            port=55000,
            timeout=0
        )

        self.config.log_level = LOG_LEVEL

        LegacyTest.client = LegacySocket(self)

        self.connection_event = threading.Event()

        self.client.on_connect = self.on_connect
        self.client.on_close = self.on_disconnect

        logger.info('connection test')
        logger.info(str(self.config))

        try:
            self.remote = LegacyTest.remote = samsungctl.Remote(self.config)
            self.remote.open()

            self.connection_event.wait(2)
            if not self.connection_event.isSet():
                LegacyTest.remote = None
                self.fail('connection TIMED_OUT')
            else:
                logger.info('connection successful')
        except:
            import traceback
            traceback.print_exc()
            LegacyTest.remote = None
            self.fail('unable to establish connection')

        import time
        time.sleep(10)

    def send_command(self, key):

        if self.remote is None:
            self.fail('NO_CONNECTION')

        event = threading.Event()

        def on_message(message):
            expected_message = b"\x00\x00\x00" + self._serialize_string(key)
            expected_message = b"\x00\x00\x00" + self._serialize_string(
                expected_message,
                True
            )

            self.assertEqual(expected_message, message)

            tv_name = self.config.name
            tv_name_len = bytearray.fromhex(hex(len(tv_name))[2:].zfill(2))

            while len(tv_name_len) < 3:
                tv_name_len = bytearray(b'\x00') + tv_name_len

            packet = (
                tv_name_len +
                tv_name.encode() +
                "\x00\x04\x00\x00\x00\x00".encode()
            )

            self.client.send(packet)
            event.set()

        self.client.on_message = on_message

        self.remote.control(key)
        event.wait(1)
        self.client.on_message = None

        if not event.isSet():
            self.fail('TIMED_OUT')

    def test_003_GET_VOLUME(self):
        LegacyTest.func = 'GetVolume'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            [['CurrentVolume', 50]]
        )
        self.assertEqual(50, self.remote.volume, 'VOLUME_NOT_50')

    def test_003_SET_VOLUME(self):
        LegacyTest.func = 'SetVolume'
        LegacyTest.result = build_xml_response(LegacyTest.func + 'Response', [])
        LegacyTest.value_check_event.clear()
        self.remote.volume = 30

        if not LegacyTest.value_check_event.isSet():
            self.fail('TIMED_OUT')

    def test_004_GET_MUTE(self):
        LegacyTest.func = 'GetMute'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            [['CurrentMute', '1']]
        )
        self.assertEqual(True, self.remote.mute, 'MUTE_NOT_TRUE')

    def test_004_SET_MUTE(self):
        LegacyTest.func = 'SetMute'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            []
        )
        LegacyTest.value_check_event.clear()
        self.remote.mute = False

        if not LegacyTest.value_check_event.isSet():
            self.fail('FAILED_TO_PROCESS')

    def test_005_GET_BRIGHTNESS(self):
        LegacyTest.func = 'GetBrightness'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            [['CurrentBrightness', 50]]
        )
        self.assertEqual(50, self.remote.brightness, 'BRIGHTNESS_NOT_50')

    def test_005_SET_BRIGHTNESS(self):
        LegacyTest.func = 'SetBrightness'
        LegacyTest.result = build_xml_response(LegacyTest.func + 'Response', [])

        LegacyTest.value_check_event.clear()
        self.remote.brightness = 50

        if not LegacyTest.value_check_event.isSet():
            self.fail('FAILED_TO_PROCESS')

    def test_006_GET_CONTRAST(self):
        LegacyTest.func = 'GetContrast'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            [['CurrentContrast', 50]]
        )
        self.assertEqual(50, self.remote.contrast, 'CONTRAST_NOT_50')

    def test_006_SET_CONTRAST(self):
        LegacyTest.func = 'SetContrast'
        LegacyTest.result = build_xml_response(LegacyTest.func + 'Response', [])

        LegacyTest.value_check_event.clear()
        self.remote.contrast = 50

        if not LegacyTest.value_check_event.isSet():
            self.fail('FAILED_TO_PROCESS')

    def test_007_GET_SHARPNESS(self):
        LegacyTest.func = 'GetSharpness'
        LegacyTest.result = build_xml_response(
            LegacyTest.func + 'Response',
            [['CurrentSharpness', 50]]
        )
        self.assertEqual(50, self.remote.sharpness, 'SHARPNESS_NOT_50')

    def test_007_SET_SHARPNESS(self):
        LegacyTest.func = 'SetSharpness'
        LegacyTest.result = build_xml_response(LegacyTest.func + 'Response', [])

        LegacyTest.value_check_event.clear()
        self.remote.sharpness = 50

        if not LegacyTest.value_check_event.isSet():
            self.fail('FAILED_TO_PROCESS')

    # @send_key
    def test_0100_KEY_POWEROFF(self):
        """Power OFF key test"""
        pass

    # @send_key
    def test_0101_KEY_POWERON(self):
        """Power On key test"""
        pass

    # @send_key
    def test_0102_KEY_POWER(self):
        """Power Toggle key test"""
        pass

    @send_key
    def test_0103_KEY_SOURCE(self):
        """Source key test"""
        pass

    @send_key
    def test_0104_KEY_COMPONENT1(self):
        """Component 1 key test"""
        pass

    @send_key
    def test_0105_KEY_COMPONENT2(self):
        """Component 2 key test"""
        pass

    @send_key
    def test_0106_KEY_AV1(self):
        """AV 1 key test"""
        pass

    @send_key
    def test_0107_KEY_AV2(self):
        """AV 2 key test"""
        pass

    @send_key
    def test_0108_KEY_AV3(self):
        """AV 3 key test"""
        pass

    @send_key
    def test_0109_KEY_SVIDEO1(self):
        """S Video 1 key test"""
        pass

    @send_key
    def test_0110_KEY_SVIDEO2(self):
        """S Video 2 key test"""
        pass

    @send_key
    def test_0111_KEY_SVIDEO3(self):
        """S Video 3 key test"""
        pass

    @send_key
    def test_0112_KEY_HDMI(self):
        """HDMI key test"""
        pass

    @send_key
    def test_0113_KEY_HDMI1(self):
        """HDMI 1 key test"""
        pass

    @send_key
    def test_0114_KEY_HDMI2(self):
        """HDMI 2 key test"""
        pass

    @send_key
    def test_0115_KEY_HDMI3(self):
        """HDMI 3 key test"""
        pass

    @send_key
    def test_0116_KEY_HDMI4(self):
        """HDMI 4 key test"""
        pass

    @send_key
    def test_0117_KEY_FM_RADIO(self):
        """FM Radio key test"""
        pass

    @send_key
    def test_0118_KEY_DVI(self):
        """DVI key test"""
        pass

    @send_key
    def test_0119_KEY_DVR(self):
        """DVR key test"""
        pass

    @send_key
    def test_0120_KEY_TV(self):
        """TV key test"""
        pass

    @send_key
    def test_0121_KEY_ANTENA(self):
        """Analog TV key test"""
        pass

    @send_key
    def test_0122_KEY_DTV(self):
        """Digital TV key test"""
        pass

    @send_key
    def test_0123_KEY_1(self):
        """Key1 key test"""
        pass

    @send_key
    def test_0124_KEY_2(self):
        """Key2 key test"""
        pass

    @send_key
    def test_0125_KEY_3(self):
        """Key3 key test"""
        pass

    @send_key
    def test_0126_KEY_4(self):
        """Key4 key test"""
        pass

    @send_key
    def test_0127_KEY_5(self):
        """Key5 key test"""
        pass

    @send_key
    def test_0128_KEY_6(self):
        """Key6 key test"""
        pass

    @send_key
    def test_0129_KEY_7(self):
        """Key7 key test"""
        pass

    @send_key
    def test_0130_KEY_8(self):
        """Key8 key test"""
        pass

    @send_key
    def test_0131_KEY_9(self):
        """Key9 key test"""
        pass

    @send_key
    def test_0132_KEY_0(self):
        """Key0 key test"""
        pass

    @send_key
    def test_0133_KEY_PANNEL_CHDOWN(self):
        """3D key test"""
        pass

    @send_key
    def test_0134_KEY_ANYNET(self):
        """AnyNet+ key test"""
        pass

    @send_key
    def test_0135_KEY_ESAVING(self):
        """Energy Saving key test"""
        pass

    @send_key
    def test_0136_KEY_SLEEP(self):
        """Sleep Timer key test"""
        pass

    @send_key
    def test_0137_KEY_DTV_SIGNAL(self):
        """DTV Signal key test"""
        pass

    @send_key
    def test_0138_KEY_CHUP(self):
        """Channel Up key test"""
        pass

    @send_key
    def test_0139_KEY_CHDOWN(self):
        """Channel Down key test"""
        pass

    @send_key
    def test_0140_KEY_PRECH(self):
        """Previous Channel key test"""
        pass

    @send_key
    def test_0141_KEY_FAVCH(self):
        """Favorite Channels key test"""
        pass

    @send_key
    def test_0142_KEY_CH_LIST(self):
        """Channel List key test"""
        pass

    @send_key
    def test_0143_KEY_AUTO_PROGRAM(self):
        """Auto Program key test"""
        pass

    @send_key
    def test_0144_KEY_MAGIC_CHANNEL(self):
        """Magic Channel key test"""
        pass

    @send_key
    def test_0145_KEY_VOLUP(self):
        """Volume Up key test"""
        pass

    @send_key
    def test_0146_KEY_VOLDOWN(self):
        """Volume Down key test"""
        pass

    @send_key
    def test_0147_KEY_MUTE(self):
        """Mute key test"""
        pass

    @send_key
    def test_0148_KEY_UP(self):
        """Navigation Up key test"""
        pass

    @send_key
    def test_0149_KEY_DOWN(self):
        """Navigation Down key test"""
        pass

    @send_key
    def test_0150_KEY_LEFT(self):
        """Navigation Left key test"""
        pass

    @send_key
    def test_0151_KEY_RIGHT(self):
        """Navigation Right key test"""
        pass

    @send_key
    def test_0152_KEY_RETURN(self):
        """Navigation Return/Back key test"""
        pass

    @send_key
    def test_0153_KEY_ENTER(self):
        """Navigation Enter key test"""
        pass

    @send_key
    def test_0154_KEY_REWIND(self):
        """Rewind key test"""
        pass

    @send_key
    def test_0155_KEY_STOP(self):
        """Stop key test"""
        pass

    @send_key
    def test_0156_KEY_PLAY(self):
        """Play key test"""
        pass

    @send_key
    def test_0157_KEY_FF(self):
        """Fast Forward key test"""
        pass

    @send_key
    def test_0158_KEY_REC(self):
        """Record key test"""
        pass

    @send_key
    def test_0159_KEY_PAUSE(self):
        """Pause key test"""
        pass

    @send_key
    def test_0160_KEY_LIVE(self):
        """Live key test"""
        pass

    @send_key
    def test_0161_KEY_QUICK_REPLAY(self):
        """fnKEY_QUICK_REPLAY key test"""
        pass

    @send_key
    def test_0162_KEY_STILL_PICTURE(self):
        """fnKEY_STILL_PICTURE key test"""
        pass

    @send_key
    def test_0163_KEY_INSTANT_REPLAY(self):
        """fnKEY_INSTANT_REPLAY key test"""
        pass

    @send_key
    def test_0164_KEY_PIP_ONOFF(self):
        """PIP On/Off key test"""
        pass

    @send_key
    def test_0165_KEY_PIP_SWAP(self):
        """PIP Swap key test"""
        pass

    @send_key
    def test_0166_KEY_PIP_SIZE(self):
        """PIP Size key test"""
        pass

    @send_key
    def test_0167_KEY_PIP_CHUP(self):
        """PIP Channel Up key test"""
        pass

    @send_key
    def test_0168_KEY_PIP_CHDOWN(self):
        """PIP Channel Down key test"""
        pass

    @send_key
    def test_0169_KEY_AUTO_ARC_PIP_SMALL(self):
        """PIP Small key test"""
        pass

    @send_key
    def test_0170_KEY_AUTO_ARC_PIP_WIDE(self):
        """PIP Wide key test"""
        pass

    @send_key
    def test_0171_KEY_AUTO_ARC_PIP_RIGHT_BOTTOM(self):
        """PIP Bottom Right key test"""
        pass

    @send_key
    def test_0172_KEY_AUTO_ARC_PIP_SOURCE_CHANGE(self):
        """PIP Source Change key test"""
        pass

    @send_key
    def test_0173_KEY_PIP_SCAN(self):
        """PIP Scan key test"""
        pass

    @send_key
    def test_0174_KEY_VCR_MODE(self):
        """VCR Mode key test"""
        pass

    @send_key
    def test_0175_KEY_CATV_MODE(self):
        """CATV Mode key test"""
        pass

    @send_key
    def test_0176_KEY_DSS_MODE(self):
        """DSS Mode key test"""
        pass

    @send_key
    def test_0177_KEY_TV_MODE(self):
        """TV Mode key test"""
        pass

    @send_key
    def test_0178_KEY_DVD_MODE(self):
        """DVD Mode key test"""
        pass

    @send_key
    def test_0179_KEY_STB_MODE(self):
        """STB Mode key test"""
        pass

    @send_key
    def test_0180_KEY_PCMODE(self):
        """PC Mode key test"""
        pass

    @send_key
    def test_0181_KEY_GREEN(self):
        """Green key test"""
        pass

    @send_key
    def test_0182_KEY_YELLOW(self):
        """Yellow key test"""
        pass

    @send_key
    def test_0183_KEY_CYAN(self):
        """Cyan key test"""
        pass

    @send_key
    def test_0184_KEY_RED(self):
        """Red key test"""
        pass

    @send_key
    def test_0185_KEY_TTX_MIX(self):
        """Teletext Mix key test"""
        pass

    @send_key
    def test_0186_KEY_TTX_SUBFACE(self):
        """Teletext Subface key test"""
        pass

    @send_key
    def test_0187_KEY_ASPECT(self):
        """Aspect Ratio key test"""
        pass

    @send_key
    def test_0188_KEY_PICTURE_SIZE(self):
        """Picture Size key test"""
        pass

    @send_key
    def test_0189_KEY_4_3(self):
        """Aspect Ratio 4:3 key test"""
        pass

    @send_key
    def test_0190_KEY_16_9(self):
        """Aspect Ratio 16:9 key test"""
        pass

    @send_key
    def test_0191_KEY_EXT14(self):
        """Aspect Ratio 3:4 (Alt) key test"""
        pass

    @send_key
    def test_0192_KEY_EXT15(self):
        """Aspect Ratio 16:9 (Alt) key test"""
        pass

    @send_key
    def test_0193_KEY_PMODE(self):
        """Picture Mode key test"""
        pass

    @send_key
    def test_0194_KEY_PANORAMA(self):
        """Picture Mode Panorama key test"""
        pass

    @send_key
    def test_0195_KEY_DYNAMIC(self):
        """Picture Mode Dynamic key test"""
        pass

    @send_key
    def test_0196_KEY_STANDARD(self):
        """Picture Mode Standard key test"""
        pass

    @send_key
    def test_0197_KEY_MOVIE1(self):
        """Picture Mode Movie key test"""
        pass

    @send_key
    def test_0198_KEY_GAME(self):
        """Picture Mode Game key test"""
        pass

    @send_key
    def test_0199_KEY_CUSTOM(self):
        """Picture Mode Custom key test"""
        pass

    @send_key
    def test_0200_KEY_EXT9(self):
        """Picture Mode Movie (Alt) key test"""
        pass

    @send_key
    def test_0201_KEY_EXT10(self):
        """Picture Mode Standard (Alt) key test"""
        pass

    @send_key
    def test_0202_KEY_MENU(self):
        """Menu key test"""
        pass

    @send_key
    def test_0203_KEY_TOPMENU(self):
        """Top Menu key test"""
        pass

    @send_key
    def test_0204_KEY_TOOLS(self):
        """Tools key test"""
        pass

    @send_key
    def test_0205_KEY_HOME(self):
        """Home key test"""
        pass

    @send_key
    def test_0206_KEY_CONTENTS(self):
        """Contents key test"""
        pass

    @send_key
    def test_0207_KEY_GUIDE(self):
        """Guide key test"""
        pass

    @send_key
    def test_0208_KEY_DISC_MENU(self):
        """Disc Menu key test"""
        pass

    @send_key
    def test_0209_KEY_DVR_MENU(self):
        """DVR Menu key test"""
        pass

    @send_key
    def test_0210_KEY_HELP(self):
        """Help key test"""
        pass

    @send_key
    def test_0211_KEY_INFO(self):
        """Info key test"""
        pass

    @send_key
    def test_0212_KEY_CAPTION(self):
        """Caption key test"""
        pass

    @send_key
    def test_0213_KEY_CLOCK_DISPLAY(self):
        """ClockDisplay key test"""
        pass

    @send_key
    def test_0214_KEY_SETUP_CLOCK_TIMER(self):
        """Setup Clock key test"""
        pass

    @send_key
    def test_0215_KEY_SUB_TITLE(self):
        """Subtitle key test"""
        pass

    @send_key
    def test_0216_KEY_ZOOM_MOVE(self):
        """Zoom Move key test"""
        pass

    @send_key
    def test_0217_KEY_ZOOM_IN(self):
        """Zoom In key test"""
        pass

    @send_key
    def test_0218_KEY_ZOOM_OUT(self):
        """Zoom Out key test"""
        pass

    @send_key
    def test_0219_KEY_ZOOM1(self):
        """Zoom 1 key test"""
        pass

    @send_key
    def test_0220_KEY_ZOOM2(self):
        """Zoom 2 key test"""
        pass

    def test_999_DISCONNECT(self):
        if self.remote is not None:
            self.remote.close()

        import requests

        self.ssdp_event.set()
        self.ssdp_sock.shutdown(socket.SHUT_RDWR)
        self.ssdp_sock.close()
        self.ssdp_thread.join(3.0)

        requests.post('http://127.0.0.1:{0}/shutdown'.format(UPNP_PORT))

        self.client.close()

    def on_disconnect(self):
        pass

    def on_connect(self, message):

        payload = (
            b"\x64\x00" +
            self._serialize_string(self.config.description) +
            self._serialize_string(self.config.id) +
            self._serialize_string(self.config.name)
        )
        packet = b"\x00\x00\x00" + self._serialize_string(payload, True)

        self.assertEqual(packet, message)

        tv_name = self.config.name
        tv_name_len = bytearray.fromhex(hex(len(tv_name))[2:].zfill(2))

        while len(tv_name_len) < 3:
            tv_name_len = bytearray(b'\x00') + tv_name_len

        packet1 = (
            tv_name_len +
            tv_name.encode() +
            "\x00\x01\x0a".encode()
        )
        packet2 = (
            tv_name_len +
            tv_name.encode() +
            "\x00\x04\x64\x00\x01\x00".encode()
        )

        self.client.send(packet1)
        self.client.send(packet2)
        self.connection_event.set()


if __name__ == '__main__':
    base_path = os.path.dirname(__file__)

    if not base_path:
        base_path = os.path.dirname(sys.argv[0])

    if not base_path:
        base_path = os.getcwd()

    sys.path.insert(0, os.path.abspath(os.path.join(base_path, '..')))

    import samsungctl

    logger = logging.getLogger('samsungctl')
    unittest.main()

    # test_loader = unittest.TestLoader()
    # websocket_test_suite = test_loader.loadTestsFromTestCase(WebSocketTest)
    # websocket_ssl_test_suite = test_loader.loadTestsFromTestCase(
    #     WebSocketSSLTest
    # )
    # legacy_test_suite = test_loader.loadTestsFromTestCase(LegacyTest)
    #
    # # Default args:
    # text_test_runner = unittest.TextTestRunner()
    # text_test_runner.run(websocket_test_suite)
    # text_test_runner.run(websocket_ssl_test_suite)
    # text_test_runner.run(legacy_test_suite)
else:
    import samsungctl

    logger = logging.getLogger('samsungctl')
