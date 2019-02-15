# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function
import logging
import threading
from .upnp.discover import auto_discover
from . import wake_on_lan
from .upnp import UPNPTV
from .utils import LogIt, LogItWithReturn

logger = logging.getLogger('samsungctl')


class WebSocketBase(UPNPTV):
    """Base class for TV's with websocket connection."""

    @LogIt
    def __init__(self, config):
        """
        Constructor.

        :param config: TV configuration settings. see `samsungctl.Config` for further details
        :type config: `dict` or `samsungctl.Config` instance
        """
        self.config = config
        self.sock = None
        self._loop_event = threading.Event()
        self.auth_lock = threading.Lock()
        self._registered_callbacks = []
        self._thread = None
        super(WebSocketBase, self).__init__(config)

        new_config, state = auto_discover.register_callback(
            self._connect,
            config.uuid
        )

        if not auto_discover.is_running:
            auto_discover.start()

        if state:
            self._connect(new_config, state)

    def _connect(self, config, power):
        if power and not self._thread:
            self.config.copy(config)

            if self.open():
                self.connect()
        elif not power:
            self.close()

    @property
    @LogItWithReturn
    def mac_address(self):
        """
        MAC Address.

        **Get:** Gets the MAC address.

            *Returns:* None or the MAC address of the TV formatted ``"00:00:00:00:00"``

            *Return type:* `None` or `str`
        """
        if self.config.mac is None:
            self.config.mac = wake_on_lan.get_mac_address(self.config.host)
            if self.config.mac is None:
                if not self.power:
                    logger.error('Unable to acquire MAC address')
        return self.config.mac

    def on_message(self, _):
        pass

    @LogIt
    def close(self):
        """Close the connection."""
        if self.sock is not None:
            self._loop_event.set()
            try:
                self.sock.close()
            except:
                pass

            if self._thread is not None:
                self._thread.join(3.0)

    def loop(self):
        while not self._loop_event.isSet():
            try:
                data = self.sock.recv()
                if data:
                    self.on_message(data)
                else:
                    raise RuntimeError
            except:
                self.disconnect()
                del self._registered_callbacks[:]

        try:
            self.sock.close()
        except:
            pass

        self.sock = None
        self._loop_event.clear()
        self._thread = None

    @property
    def artmode(self):
        return None

    @artmode.setter
    def artmode(self, value):
        pass

    @LogItWithReturn
    def power(self):
        with self.auth_lock:
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

    def control(self, *_):
        raise NotImplementedError

    def open(self):
        raise NotImplementedError

    def __enter__(self):
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
