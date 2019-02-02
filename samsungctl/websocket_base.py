# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function
import logging
import threading
import requests
from . import wake_on_lan
from .utils import LogIt, LogItWithReturn

logger = logging.getLogger('samsungctl')


class WebSocketBase(object):
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
        self._registered_callbacks = []
        self._starting = False
        self._running = False
        self._thread = None

        try:
            requests.get(
                'http://{0}:8001/api/v2/'.format(self.config.host),
                timeout=3
            )
            self.open()
        except (
            requests.HTTPError,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError
        ):
            pass

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
            self.sock.close()
            if self._thread is not None:
                self._thread.join(3.0)
            if self._thread is not None:
                raise RuntimeError('Loop thread did not properly terminate')

    def loop(self):
        self._running = True
        while not self._loop_event.isSet():
            try:
                data = self.sock.recv()
                if data:
                    self.on_message(data)
            except:
                self.sock = None
                del self._registered_callbacks[:]
                logger.info('Websocket closed')

                while self.sock is None and not self._loop_event.isSet():
                    if not self._starting:
                        try:
                            self.open()
                        except:
                            self._loop_event.wait(1.0)
                    else:
                        self._loop_event.wait(1.0)

        self._running = False
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
        return self.sock is not None

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
        self.open()
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
