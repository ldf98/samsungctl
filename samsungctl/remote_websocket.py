# -*- coding: utf-8 -*-

from __future__ import print_function
import base64
import logging
import threading
import ssl
import websocket
import requests
import time
import json
import socket
import uuid

from . import application
from . import websocket_base
from . import wake_on_lan
from .utils import LogIt, LogItWithReturn

logger = logging.getLogger(__name__)


URL_FORMAT = "ws://{}:{}/api/v2/channels/samsung.remote.control?name={}"
SSL_URL_FORMAT = "wss://{}:{}/api/v2/channels/samsung.remote.control?name={}"


class RemoteWebsocket(websocket_base.WebSocketBase):
    """Object for remote control connection."""

    @LogIt
    def __init__(self, config):
        self.receive_lock = threading.Lock()
        self.send_event = threading.Event()
        super(RemoteWebsocket, self).__init__(config)

    @property
    @LogItWithReturn
    def has_ssl(self):
        try:
            logger.debug(
                self.config.host +
                ' <-- http://{0}:8001/api/v2/'.format(self.config.host)
            )
            response = requests.get(
                'http://{0}:8001/api/v2/'.format(self.config.host),
                timeout=3
            )
            logger.debug(
                self.config.host +
                ' --> ' +
                response.content.decode('utf-8')
            )
            return (
                json.loads(
                    response.content.decode('utf-8')
                )['device']['TokenAuthSupport'] == 'true'
            )
        except (ValueError, KeyError):
            return False
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            return None

    @LogIt
    def open(self):
        with self._auth_lock:
            if self.sock is not None:
                return True

            if self.config.port == 8002:

                if self.config.token:
                    token = "&token=" + self.config.token
                else:
                    token = ''

                sslopt = {"cert_reqs": ssl.CERT_NONE}
                url = SSL_URL_FORMAT.format(
                    self.config.host,
                    self.config.port,
                    self._serialize_string(self.config.name)
                ) + token
            else:
                sslopt = {}
                url = URL_FORMAT.format(
                    self.config.host,
                    self.config.port,
                    self._serialize_string(self.config.name)
                )

            auth_event = threading.Event()
            unauth_event = threading.Event()

            def unauthorized_callback(_):
                unauth_event.set()
                auth_event.set()

            token = None

            def auth_callback(data):
                global token

                if 'data' in data and 'token' in data["data"]:
                    token = data['data']["token"]
                    logger.debug(
                        self.config.host +
                        ' -- (token) ' +
                        self.config.token
                    )

                logger.debug(
                    self.config.host +
                    ' -- access granted'
                )
                auth_event.set()

            self.register_receive_callback(
                auth_callback,
                'event',
                'ms.channel.connect'
            )

            self.register_receive_callback(
                unauthorized_callback,
                'event',
                'ms.channel.unauthorized'
            )

            logger.debug(
                self.config.host +
                ' <-- websocket url: ' +
                url +
                ' - ssl options:' +
                str(sslopt)
            )

            self._thread = threading.Thread(target=self.loop)
            self._thread.start()

            try:
                self.sock = websocket.create_connection(url, sslopt=sslopt)
            except:
                if not self.config.paired:
                    raise RuntimeError('Unable to connect to the TV')

                return False

            if self.config.paired:
                auth_event.wait(5.0)
            else:
                auth_event.wait(30.0)

            self.unregister_receive_callback(
                unauthorized_callback,
                'event',
                'ms.channel.unauthorized'
            )
            self.unregister_receive_callback(
                auth_callback,
                'event',
                'ms.channel.connect'
            )

            if not auth_event.isSet() or unauth_event.isSet():
                self.close()

                if not self.config.paired:
                    if self.config.port == 8001 and self.has_ssl:
                        logger.debug(
                            self.config.host +
                            ' -- trying SSL connection.'
                        )
                        self.config.port = 8002
                        return self.open()

                    raise RuntimeError('Auth Failure')

                return False

            self.config.token = token
            self.config.paired = True

            if self.config.path:
                self.config.save()

            self.send_event.wait(0.5)
            self.connect()
            return True

    @LogIt
    def send(self, method, **params):
        if self.sock is None:
            logger.info(
                self.config.host +
                ' -- is the TV on?!?'
            )
            return False

        with self._send_lock:
            payload = dict(
                method=method,
                params=params
            )
            logger.debug(
                self.config.host +
                ' <-- ' +
                str(payload)
            )

            try:
                self.sock.send(json.dumps(payload))
                self.send_event.wait(0.3)
            except:
                pass

    @LogIt
    def _set_power(self, value):
        """
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"Click",
                "DataOfCmd":"KEY_POWER",
                "Option":"false",
                "TypeOfRemote":"SendRemoteKey"
            }
        }
        """
        event = threading.Event()

        if value and not self.power:
            if self.mac_address:
                count = 0
                wake_on_lan.send_wol(self.mac_address)
                event.wait(1.0)

                while not self.power and count < 20:
                    wake_on_lan.send_wol(self.mac_address)
                    event.wait(1.0)
                    count += 1

                if count == 20:
                    logger.error(
                        self.config.model +
                        ' -- unable to power on the TV, '
                        'check network connectivity'
                    )
            else:
                logging.error(
                    self.config.host +
                    ' -- unable to get TV\'s mac address'
                )

        elif not value and self.power:
            count = 0
            power_off = dict(
                Cmd='Click',
                DataOfCmd='KEY_POWEROFF',
                Option="false",
                TypeOfRemote="SendRemoteKey"
            )
            power = dict(
                Cmd='Click',
                DataOfCmd='KEY_POWER',
                Option="false",
                TypeOfRemote="SendRemoteKey"
            )

            self.send("ms.remote.control", **power)
            # self.send("ms.remote.control", **power_off)
            event.wait(2.0)

            while self.power and count < 20:
                event.wait(1.0)
                count += 1

            if count == 20:
                logger.info(
                    self.config.host +
                    ' unable to power off the TV'
                )

    def _send_key(self, key, cmd='Click'):
        """
        Send a control command.
        cmd can be one of the following


        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"Click", "Press" or "Release",
                "DataOfCmd":"KEY_*",
                "Option":"false",
                "TypeOfRemote":"SendRemoteKey"
            }
        }

        """

        params = dict(
            Cmd=cmd,
            DataOfCmd=key,
            Option="false",
            TypeOfRemote="SendRemoteKey"
        )

        self.send("ms.remote.control", **params)

    _key_interval = 0.5

    @LogItWithReturn
    def get_application(self, pattern):
        for app in self.applications:
            if pattern in (app.app_id, app.name):
                return app

    @property
    @LogItWithReturn
    def applications(self):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "data":"",
                "event":"ed.edenApp.get",
                "to":"host",
            }
        }
        {
            "method":"ms.channel.emit",
            "params":{
                "data":"",
                "event":"ed.installedApp.get",
                "to":"host",
            }
        }

        """
        eden_event = threading.Event()
        installed_event = threading.Event()

        eden_data = []
        installed_data = []

        @LogIt
        def eden_app_get(data):
            if 'data' in data:
                eden_data.extend(data['data']['data'])
            eden_event.set()

        @LogIt
        def installed_app_get(data):
            if 'data' in data:
                installed_data.extend(data['data']['data'])
            installed_event.set()

        self.register_receive_callback(
            eden_app_get,
            'event',
            'ed.edenApp.get'
        )
        self.register_receive_callback(
            installed_app_get,
            'event',
            'ed.installedApp.get'
        )

        for event in ['ed.edenApp.get', 'ed.installedApp.get']:
            params = dict(
                data='',
                event=event,
                to='host'
            )

            self.send('ms.channel.emit', **params)

        eden_event.wait(30.0)
        installed_event.wait(30.0)

        self.unregister_receive_callback(
            eden_app_get,
            'event',
            'ed.edenApp.get'
        )

        self.unregister_receive_callback(
            installed_app_get,
            'data',
            None
        )

        if not eden_event.isSet():
            logger.debug(
                self.config.host +
                ' -- (ed.edenApp.get) timed out'
            )

        if not installed_event.isSet():
            logger.debug(
                self.config.host +
                ' -- (ed.installedApp.get) timed out'
            )

        if eden_data and installed_data:
            updated_apps = []

            for eden_app in eden_data[:]:
                for installed_app in installed_data[:]:
                    if eden_app['appId'] == installed_app['appId']:
                        installed_data.remove(installed_app)
                        eden_data.remove(eden_app)
                        eden_app.update(installed_app)
                        updated_apps += [eden_app]
                        break
        else:
            updated_apps = []

        updated_apps += eden_data + installed_data

        for app in updated_apps[:]:
            updated_apps.remove(app)
            updated_apps += [application.Application(self, **app)]

        return updated_apps

    @LogIt
    def register_receive_callback(self, callback, key, data):
        self._registered_callbacks += [[callback, key, data]]

    @LogIt
    def unregister_receive_callback(self, callback, key, data):
        if [callback, key, data] in self._registered_callbacks:
            self._registered_callbacks.remove([callback, key, data])

    @LogIt
    def on_message(self, message):
        response = json.loads(message)

        for callback, key, data in self._registered_callbacks[:]:
            if key in response and (data is None or response[key] == data):
                callback(response)
                self._registered_callbacks.remove([callback, key, data])
                break
        else:
            if 'params' in response and 'event' in response['params']:
                event = response['params']['event']

                if event == 'd2d_service_message':
                    data = json.loads(response['params']['data'])

                    if 'event' in data:
                        for callback, key, _ in self._registered_callbacks[:]:
                            if key == data['event']:
                                callback(data)
                                self._registered_callbacks.remove(
                                    [callback, key, None]
                                )
                                break

    def _build_art_app_request(self, request, value=None):
        if value is None:
            data = dict(
                request=request,
                id=str(uuid.uuid4())[1:-1]
            )
        else:
            data = dict(
                request=request,
                value=value,
                id=str(uuid.uuid4())[1:-1]
            )

        return dict(
            clientIp=socket.gethostbyname(socket.gethostname()),
            data=json.dumps(data),
            deviceName=self._serialize_string(self.config.name),
            event='art_app_request',
            to='host'
        )

    @property
    def motion_timer(self):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"request\":\"get_motion_timer\",
                    \"id\":\"30852acd-1b7d-4496-8bef-53e1178fa839\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }"
        """

        params = self._build_art_app_request('get_motion_timer')

        response = []
        event = threading.Event()

        def motion_timer_callback(data):
            """
            {
                "method":"ms.channel.emit",
                "params":{
                    "clientIp":"127.0.0.1",
                    "data":"{
                        \"id\":\"259320d8-f368-48a4-bf03-789f24a22c0f\",
                        \"event\":\"motion_timer\",
                        \"value\":\"30\",
                        \"valid_values\":\"[\\\"off\\\",\\\"15\\\",\\\"30\\\",\\\"60\\\",\\\"120\\\",\\\"240\\\"]\\n\",
                        \"target_client_id\":\"84b12082-5f28-461e-8e81-b98ad1c1ffa\"
                    }",
                    "deviceName":"Smart Device",
                    "event":"d2d_service_message",
                    "to":"84b12082-5f28-461e-8e81-b98ad1c1ffa"
                }
            }
            """

            valid_values = []

            for item in data['valid_values']:
                if item.isdigit():
                    item = int(item)
                valid_values += [item]

            if data['value'].isdigit():
                data['value'] = int(data['value'])

            response.append(
                dict(
                    value=int(data['value']),
                    valid_values=valid_values[:]

                )
            )

            event.set()

        self.register_receive_callback(
            motion_timer_callback,
            'motion_timer',
            None
        )

        self.send('ms.channel.emit', **params)

        event.wait(2.0)

        self.unregister_receive_callback(
            motion_timer_callback,
            'motion_timer',
            None
        )

        if not event.isSet():
            logging.debug(
                self.config.host +
                ' -- (get_motion_timer) timed out'
            )
        else:
            return response[0]

    @motion_timer.setter
    def motion_timer(self, value):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
                    \"value\":\"off\",
                    \"request\":\"set_motion_timer\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }
        """

        if value != 'off':
            value = int(value)

        res = self.motion_timer

        if res and value in res['valid_values']:
            params = self._build_art_app_request(
                'set_motion_timer',
                str(value)
            )

            self.send('ms.channel.emit', **params)

    @property
    def motion_sensitivity(self):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"request\":\"get_motion_sensitivity\",
                    \"id\":\"30852acd-1b7d-4496-8bef-53e1178fa839\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }"
        """

        params = self._build_art_app_request('get_motion_sensitivity')

        response = []
        event = threading.Event()

        def motion_sensitivity_callback(data):
            """
            {
                "method":"ms.channel.emit",
                "params":{
                    "clientIp":"127.0.0.1",
                    "data":"{
                        \"id\":\"259320d8-f368-48a4-bf03-789f24a22c0f\",
                        \"event\":\"motion_sensitivity\",
                        \"value\":\"2\",
                        \"min\":\"1\",
                        \"max\":\"3\",
                        \"target_client_id\":\"84b12082-5f28-461e-8e81-b98ad1c1ffa\"
                    }",
                    "deviceName":"Smart Device",
                    "event":"d2d_service_message",
                    "to":"84b12082-5f28-461e-8e81-b98ad1c1ffa"
                }
            }
            """
            response.append(
                dict(
                    value=int(data['value']),
                    min=int(data['min']),
                    max=int(data['max'])
                )
            )

            event.set()

        self.register_receive_callback(
            motion_sensitivity_callback,
            'motion_sensitivity',
            None
        )

        self.send('ms.channel.emit', **params)

        event.wait(2.0)

        self.unregister_receive_callback(
            motion_sensitivity_callback,
            'motion_sensitivity',
            None
        )

        if not event.isSet():
            logging.debug(
                self.config.host +
                ' -- (get_motion_sensitivity) timed out'
            )
        else:
            return response[0]

    @motion_sensitivity.setter
    def motion_sensitivity(self, value):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
                    \"value\":\"2\",
                    \"request\":\"set_motion_sensitivity\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }
        """
        value = int(value)

        res = self.motion_sensitivity
        if res and res['min'] <= value <= res['max']:
            params = self._build_art_app_request(
                'set_motion_sensitivity',
                str(value)
            )

            self.send('ms.channel.emit', **params)

    # @property
    # def color_temperature(self):
    #     """
    #     {
    #         "method":"ms.channel.emit",
    #         "params":{
    #             "clientIp":"192.168.1.20",
    #             "data":"{
    #                 \"request\":\"get_color_temperature\",
    #                 \"id\":\"30852acd-1b7d-4496-8bef-53e1178fa839\"
    #             }",
    #             "deviceName":"W1Bob25lXWlQaG9uZQ==",
    #             "event":"art_app_request",
    #             "to":"host"
    #         }
    #     }"
    #     """
    #
    #     params = self._build_art_app_request('get_color_temperature')
    #
    #     response = []
    #     event = threading.Event()
    #
    #     def color_temperature_callback(data):
    #         """
    #         {
    #             "method":"ms.channel.emit",
    #             "params":{
    #                 "clientIp":"127.0.0.1",
    #                 "data":"{
    #                     \"id\":\"259320d8-f368-48a4-bf03-789f24a22c0f\",
    #                     \"event\":\"color_temperature\",
    #                     \"value\":\"2\",
    #                     \"min\":\"1\",
    #                     \"max\":\"3\",
    #                     \"target_client_id\":\"84b12082-5f28-461e-8e81-b98ad1c1ffa\"
    #                 }",
    #                 "deviceName":"Smart Device",
    #                 "event":"d2d_service_message",
    #                 "to":"84b12082-5f28-461e-8e81-b98ad1c1ffa"
    #             }
    #         }
    #         """
    #         response.append(
    #             dict(
    #                 value=int(data['value']),
    #                 min=int(data['min']),
    #                 max=int(data['max'])
    #             )
    #         )
    #
    #         event.set()
    #
    #     self.register_receive_callback(
    #         color_temperature_callback,
    #         'color_temperature',
    #         None
    #     )
    #
    #     self.send('ms.channel.emit', **params)
    #
    #     event.wait(2.0)
    #
    #     self.unregister_receive_callback(
    #         color_temperature_callback,
    #         'color_temperature',
    #         None
    #     )
    #
    #     if not event.isSet():
    #         logging.debug(
    #             self.config.host +
    #             ' -- (get_color_temperature) timed out'
    #         )
    #     else:
    #         return response[0]
    #
    # @color_temperature.setter
    # def color_temperature(self, value):
    #     """
    #     {
    #         "method":"ms.channel.emit",
    #         "params":{
    #             "clientIp":"192.168.1.20",
    #             "data":"{
    #                 \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
    #                 \"value\":\"2\",
    #                 \"request\":\"set_color_temperature\"
    #             }",
    #             "deviceName":"W1Bob25lXWlQaG9uZQ==",
    #             "event":"art_app_request",
    #             "to":"host"
    #         }
    #     }
    #     """
    #     value = int(value)
    #
    #     res = self.color_temperature
    #     if res and res['min'] <= value <= res['max']:
    #         params = self._build_art_app_request(
    #             'set_color_temperature',
    #             str(value)
    #         )
    #
    #         self.send('ms.channel.emit', **params)
    #
    # @property
    # def brightness(self):
    #     """
    #     {
    #         "method":"ms.channel.emit",
    #         "params":{
    #             "clientIp":"192.168.1.20",
    #             "data":"{
    #                 \"request\":\"get_brightness\",
    #                 \"id\":\"30852acd-1b7d-4496-8bef-53e1178fa839\"
    #             }",
    #             "deviceName":"W1Bob25lXWlQaG9uZQ==",
    #             "event":"art_app_request",
    #             "to":"host"
    #         }
    #     }"
    #     """
    #
    #     params = self._build_art_app_request('get_brightness')
    #
    #     response = []
    #     event = threading.Event()
    #
    #     def brightness_callback(data):
    #         """
    #         {
    #             "method":"ms.channel.emit",
    #             "params":{
    #                 "clientIp":"127.0.0.1",
    #                 "data":"{
    #                     \"id\":\"259320d8-f368-48a4-bf03-789f24a22c0f\",
    #                     \"event\":\"brightness\",
    #                     \"value\":\"2\",
    #                     \"min\":\"1\",
    #                     \"max\":\"3\",
    #                     \"target_client_id\":\"84b12082-5f28-461e-8e81-b98ad1c1ffa\"
    #                 }",
    #                 "deviceName":"Smart Device",
    #                 "event":"d2d_service_message",
    #                 "to":"84b12082-5f28-461e-8e81-b98ad1c1ffa"
    #             }
    #         }
    #         """
    #         response.append(
    #             dict(
    #                 value=int(data['value']),
    #                 min=int(data['min']),
    #                 max=int(data['max'])
    #             )
    #         )
    #
    #         event.set()
    #
    #     self.register_receive_callback(
    #         brightness_callback,
    #         'brightness',
    #         None
    #     )
    #
    #     self.send('ms.channel.emit', **params)
    #
    #     event.wait(2.0)
    #
    #     self.unregister_receive_callback(
    #         brightness_callback,
    #         'brightness',
    #         None
    #     )
    #
    #     if not event.isSet():
    #         logging.debug('get_brightness: timed out')
    #     else:
    #         return response[0]
    #
    # @brightness.setter
    # def brightness(self, value):
    #     """
    #     {
    #         "method":"ms.channel.emit",
    #         "params":{
    #             "clientIp":"192.168.1.20",
    #             "data":"{
    #                 \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
    #                 \"value\":\"2\",
    #                 \"request\":\"set_brightness\"
    #             }",
    #             "deviceName":"W1Bob25lXWlQaG9uZQ==",
    #             "event":"art_app_request",
    #             "to":"host"
    #         }
    #     }
    #     """
    #     value = int(value)
    #
    #     res = self.brightness
    #     if res and res['min'] <= value <= res['max']:
    #         params = self._build_art_app_request(
    #             'set_brightness',
    #             str(value)
    #         )
    #
    #         self.send('ms.channel.emit', **params)

    @property
    def brightness_sensor(self):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"request\":\"get_brightness_sensor_setting\",
                    \"id\":\"713fe2f1-2848-4161-b04c-18dd6753ecaf\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }
        """

        params = self._build_art_app_request('get_brightness_sensor_setting')

        response = []
        event = threading.Event()

        def brightness_sensor_callback(data):
            """
            {
                "method":"ms.channel.emit",
                "params":{
                    "clientIp":"127.0.0.1",
                    "data":"{
                        \"id\":\"713fe2f1-2848-4161-b04c-18dd6753ecaf\",
                        \"event\":\"brightness_sensor_setting\",
                        \"value\":\"off\",
                        \"target_client_id\":\"de34a6-2b5f-46a0-ad19-f1a3d56167\"
                    }",
                    "deviceName":"Smart Device",
                    "event":"d2d_service_message",
                    "to":"de34a6-2b5f-46a0-ad19-f1a3d56167"
                }
            }
            """

            if data['value'] == 'on':
                response.append(True)
            else:
                response.append(False)

            event.set()

        self.register_receive_callback(
            brightness_sensor_callback,
            'brightness_sensor_setting',
            None
        )

        self.send('ms.channel.emit', **params)

        event.wait(2.0)

        self.unregister_receive_callback(
            brightness_sensor_callback,
            'brightness_sensor_setting',
            None
        )

        if not event.isSet():
            logging.debug(
                self.config.host +
                ' -- (get_brightness_sensor_setting) timed out'
            )
        else:
            return response[0]

    @brightness_sensor.setter
    def brightness_sensor(self, value):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
                    \"value\":\"on\",
                    \"request\":\"set_brightness_sensor_setting\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }
        """

        params = self._build_art_app_request(
            'set_brightness_sensor_setting',
            'on' if value else 'off'
        )

        self.send('ms.channel.emit', **params)

    @property
    def artmode(self):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"request\":\"get_artmode_status\",
                    \"id\":\"30852acd-1b7d-4496-8bef-53e1178fa839\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }"
        """

        params = self._build_art_app_request('get_artmode_status')

        response = []
        event = threading.Event()

        def artmode_callback(data):
            """
            {
                "method":"ms.channel.emit",
                "params":{
                    "clientIp":"127.0.0.1",
                    "data":"{
                        \"id\":\"259320d8-f368-48a4-bf03-789f24a22c0f\",
                        \"event\":\"artmode_status\",
                        \"value\":\"off\",
                        \"target_client_id\":\"84b12082-5f28-461e-8e81-b98ad1c1ffa\"
                    }",
                    "deviceName":"Smart Device",
                    "event":"d2d_service_message",
                    "to":"84b12082-5f28-461e-8e81-b98ad1c1ffa"
                }
            }
            """

            if data['value'] == 'on':
                response.append(True)
            else:
                response.append(False)

            event.set()

        self.register_receive_callback(
            artmode_callback,
            'artmode_status',
            None
        )

        self.send('ms.channel.emit', **params)

        event.wait(2.0)

        self.unregister_receive_callback(
            artmode_callback,
            'artmode_status',
            None
        )

        if not event.isSet():
            logging.debug(
                self.config.host +
                ' -- (get_artmode_status) timed out'
            )
        else:
            return response[0]

    @artmode.setter
    def artmode(self, value):
        """
        {
            "method":"ms.channel.emit",
            "params":{
                "clientIp":"192.168.1.20",
                "data":"{
                    \"id\":\"545fc0c1-bd9b-48f5-8444-02f9c519aaec\",
                    \"value\":\"on\",
                    \"request\":\"set_artmode_status\"
                }",
                "deviceName":"W1Bob25lXWlQaG9uZQ==",
                "event":"art_app_request",
                "to":"host"
            }
        }
        """

        params = self._build_art_app_request(
            'set_artmode_status',
            'on' if value else 'off'
        )

        self.send('ms.channel.emit', **params)

    @LogIt
    def input_text(self, text):
        """
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":base64.b64encode,
                "TypeOfRemote":"SendInputString",
                "DataOfCmd":"base64",
            }
        }
        """

        params = dict(
            Cmd=self._serialize_string(text),
            TypeOfRemote="SendInputString",
            DataOfCmd="base64"
        )

        self.send('ms.remote.control', **params)

    @LogIt
    def start_voice_recognition(self):
        """Activates voice recognition.

        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"Press",
                "TypeOfRemote":"SendRemoteKey",
                "DataOfCmd":"KEY_BT_VOICE",
                "Option":"false"
            }
        }

        """
        event = threading.Event()

        def voice_callback(_):
            event.set()

        self.register_receive_callback(
            voice_callback,
            'event',
            'ms.voiceApp.standby'
        )

        params = dict(
            Cmd='Press',
            DataOfCmd='KEY_BT_VOICE',
            Option="false",
            TypeOfRemote="SendRemoteKey"
        )

        self.send("ms.remote.control", **params)

        event.wait(2.0)
        self.unregister_receive_callback(
            voice_callback,
            'event',
            'ms.voiceApp.standby'
        )

        if not event.isSet():
            logger.debug(
                self.config.host +
                ' -- (ms.voiceApp.standby) timed out'
            )

    @LogIt
    def stop_voice_recognition(self):
        """Activates voice recognition.
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"Release",
                "TypeOfRemote":"SendRemoteKey",
                "DataOfCmd":"KEY_BT_VOICE",
                "Option":"false"
            }
        }
        """

        event = threading.Event()

        def voice_callback(_):
            event.set()

        self.register_receive_callback(
            voice_callback,
            'event',
            'ms.voiceApp.hide'
        )

        params = dict(
            Cmd='Release',
            DataOfCmd='KEY_BT_VOICE',
            Option="false",
            TypeOfRemote="SendRemoteKey"
        )

        self.send("ms.remote.control", **params)

        event.wait(2.0)
        self.unregister_receive_callback(
            voice_callback,
            'event',
            'ms.voiceApp.hide'
        )
        if not event.isSet():
            logger.debug(
                self.config.host +
                ' -- (ms.voiceApp.hide) timed out'
            )

    @staticmethod
    def _serialize_string(string):
        if isinstance(string, str):
            string = str.encode(string)

        return base64.b64encode(string).decode("utf-8")

    @property
    @LogItWithReturn
    def mouse(self):
        return Mouse(self)


class Mouse(object):

    @LogIt
    def __init__(self, remote):
        self._remote = remote
        self._is_running = False
        self._commands = []
        self._ime_start_event = threading.Event()
        self._ime_update_event = threading.Event()
        self._touch_enable_event = threading.Event()
        self._send_event = threading.Event()

    @property
    @LogItWithReturn
    def is_running(self):
        return self._is_running

    @LogIt
    def clear(self):
        if not self.is_running:
            del self._commands[:]

    @LogIt
    def _send(self, cmd, **kwargs):
        """Send a control command."""
        if not self.is_running:
            params = dict(
                Cmd=cmd,
                TypeOfRemote="ProcessMouseDevice"
            )
            params.update(kwargs)

            payload = dict(
                method="ms.remote.control",
                params=params
            )

            self._commands += [payload]

    @LogIt
    def left_click(self):
        """
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"LeftClick",
                "TypeOfRemote":"ProcessMouseDevice"
            }
        }
        """
        self._send('LeftClick')

    @LogIt
    def right_click(self):
        """
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"RightClick",
                "TypeOfRemote":"ProcessMouseDevice"
            }
        }
        """
        self._send('RightClick')

    @LogIt
    def move(self, x, y):
        """
        {
            "method":"ms.remote.control",
            "params":{
                "Cmd":"Move",
                "x": 0,
                "y": 0,
                "Time": time.time,
                "TypeOfRemote":"ProcessMouseDevice"
            }
        }
        """
        position = dict(
            x=x,
            y=y,
            Time=str(time.time())
        )

        self._send('Move', Position=position)

    @LogIt
    def add_wait(self, wait):
        if self._is_running:
            self._commands += [wait]

    @LogIt
    def stop(self):
        if self.is_running:
            self._send_event.set()
            self._ime_start_event.set()
            self._ime_update_event.set()
            self._touch_enable_event.set()

    @LogIt
    def run(self):
        if not self.is_running:
            self._send_event.clear()
            self._ime_start_event.clear()
            self._ime_update_event.clear()
            self._touch_enable_event.clear()

            self._is_running = True

            @LogIt
            def ime_start(_):
                self._ime_start_event.set()

            @LogIt
            def ime_update(_):
                self._ime_update_event.set()

            @LogIt
            def touch_enable(_):
                self._touch_enable_event.set()

            self._remote.register_receive_callback(
                ime_start,
                'event',
                'ms.remote.imeStart'
            )

            self._remote.register_receive_callback(
                ime_update,
                'event',
                'ms.remote.imeUpdate'
            )

            self._remote.register_receive_callback(
                touch_enable,
                'event',
                'ms.remote.touchEnable'
            )

            for payload in self._commands:
                if isinstance(payload, (float, int)):
                    self._send_event.wait(payload)
                    if self._send_event.isSet():
                        self._is_running = False
                        return
                else:
                    self._remote.send(**payload)

                self._ime_start_event.wait(len(self._commands))
                self._ime_update_event.wait(len(self._commands))
                self._touch_enable_event.wait(len(self._commands))

                self._remote.unregister_receive_callback(
                    ime_start,
                    'event',
                    'ms.remote.imeStart'
                )

                self._remote.unregister_receive_callback(
                    ime_update,
                    'event',
                    'ms.remote.imeUpdate'
                )

                self._remote.unregister_receive_callback(
                    touch_enable,
                    'event',
                    'ms.remote.touchEnable'
                )

                self._is_running = False
