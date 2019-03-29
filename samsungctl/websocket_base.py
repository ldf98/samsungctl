# -*- coding: utf-8 -*-

from __future__ import print_function
import logging
import threading
import json
import ssl
import uuid
import base64
import websocket
import socket
from .upnp.discover import auto_discover
from . import wake_on_lan
from .upnp import UPNPTV
from .utils import LogIt, LogItWithReturn

logger = logging.getLogger(__name__)


# noinspection PyAbstractClass
class WebSocketBase(UPNPTV):
    """Base class for TV's with websocket connection."""

    @LogIt
    def __init__(self, config):
        """
        Constructor.

        :param config: TV configuration settings. see `samsungctl.Config` for
        further details
        :type config: `dict` or `samsungctl.Config` instance
        """
        self.config = config
        self.sock = None
        self._power_event = threading.Event()
        self._loop_event = threading.Event()
        self._auth_lock = threading.RLock()
        self._connect_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._registered_callbacks = []
        self._thread = None
        self._art_mode = None

        UPNPTV.__init__(self, config)

        auto_discover.register_callback(
            self._connect,
            config.uuid
        )

        self.open()

    def _connect(self, config, power):
        with self._connect_lock:
            if config is None:
                return

            if power:
                if not self._thread:
                    self.config.copy(config)
                    self.open()

                elif not self.is_connected:
                    self.connect()

            elif not power and self._thread:
                self._close_connection()
                if self._art_mode is not None:
                    self._art_mode.close()

    def _send_key(self, *args, **kwargs):
        raise NotImplementedError

    @property
    @LogItWithReturn
    def mac_address(self):
        """
        MAC Address.

        **Get:** Gets the MAC address.

            *Returns:* None or the MAC address of the TV formatted
            ``"00:00:00:00:00"``

            *Return type:* `None` or `str`
        """
        if self.config.mac is None:
            self.config.mac = wake_on_lan.get_mac_address(self.config.host)
            if self.config.mac is None:
                if not self.power:
                    logger.error(
                        self.config.host +
                        ' -- unable to acquire MAC address'
                    )
        return self.config.mac

    def on_message(self, _):
        raise NotImplementedError

    def _close_connection(self):
        self._loop_event.set()

        if self.sock is not None:
            # noinspection PyPep8,PyBroadException
            try:
                self.sock.close()
            except:
                pass

        if self._thread is not None:
            self._thread.join(3.0)

    @LogIt
    def close(self):
        """Close the connection."""
        with self._auth_lock:
            self._close_connection()
            auto_discover.unregister_callback(self._connect, self.config.uuid)
            self._power_event.clear()

    def loop(self):
        self._loop_event.clear()

        while self.sock is None and not self._loop_event.isSet():
            self._loop_event.wait(0.1)

        while not self._loop_event.isSet():
            # noinspection PyPep8,PyBroadException
            try:
                data = self.sock.recv()
            except:
                break

            else:
                if data:
                    logger.debug(
                        self.config.host +
                        ' --> ' +
                        data
                    )
                    self.on_message(data)
                else:
                    if self.config.method == 'legacy':
                        break
                    else:
                        self._loop_event.wait(0.1)

        # noinspection PyPep8,PyBroadException
        try:
            self.sock.close()
        except:
            pass

        self.sock = None
        self._thread = None
        self.disconnect()
        if not self._loop_event.isSet():
            self.open()

    @property
    @LogItWithReturn
    def power(self):
        with self._auth_lock:
            return self.sock is not None
        # try:
        #     requests.get(
        #         'http://{0}:8001/api/v2/'.format(self.config.host),
        #         timeout=2
        #     )
        #     return True
        # except (
        #     requests.HTTPError,
        #     requests.exceptions.ConnectTimeout,
        #     requests.exceptions.ConnectionError
        # ):
        #     return False

    @power.setter
    @LogIt
    def power(self, value):
        with self._auth_lock:
            if value and not self.power:
                if self._cec is not None:
                    self._cec.tv.power = True
                elif self.open():
                    self._send_key('KEY_POWERON')
                else:
                    self._set_power(value)
            elif not value and self.power:
                self._set_power(value)
                self._close_connection()
                event = threading.Event()
                event.wait(3.0)

    def _set_power(self, value):
        raise NotImplementedError

    @LogItWithReturn
    def control(self, key, *args, **kwargs):
        with self._auth_lock:
            if key == 'KEY_POWERON':
                if not self.power:
                    self.power = True
                    return True

                return False

            elif key == 'KEY_POWEROFF':
                if self.power:
                    self.power = False
                    return True

                return False

            elif key == 'KEY_POWER':
                self.power = not self.power
                return True

            elif self.sock is None:
                logger.info(
                    self.config.model +
                    ' -- is the TV on?!?'
                )
                return False

            return self._send_key(key, *args, **kwargs)

    def open(self):
        raise NotImplementedError

    def __enter__(self):
        # noinspection PyUnresolvedReferences
        """
        Open the connection to the TV. use in a `with` statement

        >>> with samsungctl.Remote(config) as remote:
        >>>     remote.KEY_MENU()


        :return: self
        :rtype: :class: `samsungctl.Remote` instance
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        This gets called automatically when exiting a `with` statement
        see `samsungctl.Remote.__enter__` for more information

        :param exc_type: Not Used
        :param exc_val: Not Used
        :param exc_tb: Not Used
        :return: `None`
        """
        self.close()


class AuxWebsocketBase(object):

    def __init__(self, config, url, sslurl):
        self.sock = None
        self.config = config
        self._thread = None
        self._id = str(uuid.uuid4())[1:-1]
        self._client_ip = socket.gethostbyname(socket.gethostname())
        self._device_name = self._serialize_string(config.name)
        self._loop_event = threading.Event()
        self._send_lock = threading.Lock()
        self._send_event = threading.Event()
        self._registered_callbacks = []
        self._url = url
        self._sslurl = sslurl

        self.open()

    @LogIt
    def close(self):
        """Close the connection."""
        self._loop_event.set()

        if self.sock is not None:
            # noinspection PyPep8,PyBroadException
            try:
                self.sock.close()
            except:
                pass

        if self._thread is not None:
            self._thread.join(3.0)

    def loop(self):
        self._loop_event.clear()

        while self.sock is None and not self._loop_event.isSet():
            self._loop_event.wait(0.1)

        while not self._loop_event.isSet():
            # noinspection PyPep8,PyBroadException
            try:
                data = self.sock.recv()
            except:
                break

            else:
                if data:
                    logger.debug(
                        self.config.host +
                        ' --> ' +
                        data
                    )
                    self.on_message(data)
                else:
                    self._loop_event.wait(0.1)

        # noinspection PyPep8,PyBroadException
        try:
            self.sock.close()
        except:
            pass

        self.sock = None
        self._thread = None
        if not self._loop_event.isSet():
            self.open()

    def on_message(self, _):
        raise NotImplementedError

    @LogIt
    def register_receive_callback(self, callback, key, data):
        self._registered_callbacks += [[callback, key, data]]

    @LogIt
    def unregister_receive_callback(self, callback, key, data):
        if [callback, key, data] in self._registered_callbacks:
            self._registered_callbacks.remove([callback, key, data])

    @LogIt
    def open(self):
        if self.sock is not None:
            return True

        if self.config.port == 8002:
            if self.config.token:
                token = "&token=" + str(self.config.token)
            else:
                token = ''

            sslopt = {"cert_reqs": ssl.CERT_NONE}
            url = self._sslurl.format(
                self.config.host,
                self.config.port,
                self._serialize_string(self.config.name)
            ) + token
        else:
            sslopt = {}
            url = self._url.format(
                self.config.host,
                self.config.port,
                self._serialize_string(self.config.name)
            )

        auth_event = threading.Event()

        @LogItWithReturn
        def auth_callback(_):
            auth_event.set()

        del self._registered_callbacks[:]

        self.register_receive_callback(
            auth_callback,
            'event',
            'ms.channel.ready'
        )

        logger.debug(
            self.config.host +
            ' <-- url: ' +
            url +
            ' - ssl options:' +
            str(sslopt)
        )

        self._thread = threading.Thread(target=self.loop)
        self._thread.start()

        # noinspection PyPep8,PyBroadException
        try:
            self.sock = websocket.create_connection(url, sslopt=sslopt)
        except:
            self.close()
            return False

        auth_event.wait(10.0)

        self.unregister_receive_callback(
            auth_callback,
            'event',
            'ms.channel.ready'
        )

        if auth_event.isSet():
            return True

        self.close()
        return False

    @staticmethod
    def _serialize_string(string):
        if isinstance(string, str):
            string = str.encode(string)

        return base64.b64encode(string).decode("utf-8")

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

            # noinspection PyPep8,PyBroadException
            try:
                self.sock.send(json.dumps(payload))
                self._send_event.wait(0.3)
            except:
                pass
