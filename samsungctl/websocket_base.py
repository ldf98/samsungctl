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
        self.config = config
        self._mac_address = None

    @property
    @LogItWithReturn
    def mac_address(self):
        if self._mac_address is None:
            _mac_address = wake_on_lan.get_mac_address(self.config.host)
            print(_mac_address)
            if _mac_address is None:
                _mac_address = ''

            self._mac_address = _mac_address

        return self._mac_address

    @property
    @LogItWithReturn
    def power(self):
        try:
            requests.get(
                'http://{0}:8001/api/v2/'.format(self.config.host),
                timeout=3
            )
            return True
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            return False

    @power.setter
    @LogIt
    def power(self, value):
        event = threading.Event()

        if value and not self.power:
            if self.mac_address:
                count = 0
                wake_on_lan.send_wol(self.mac_address)
                event.wait(10)

                while not self.power and count < 10:
                    wake_on_lan.send_wol(self.mac_address)
                    event.wait(2.0)

                if count == 10:
                    logger.error(
                        'Unable to power on the TV, '
                        'check network connectivity'
                    )

        elif not value and self.power:
            count = 0
            while self.power and count < 10:
                self.control('KEY_POWER')
                self.control('KEY_POWEROFF')
                event.wait(2.0)

            if count == 10:
                logger.info('Unable to power off the TV')

    def control(self, *_):
        raise NotImplementedError

    def open(self):
        raise NotImplementedError

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        raise NotImplementedError
