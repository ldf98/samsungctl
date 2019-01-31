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

    @property
    @LogItWithReturn
    def power(self):
        """
        Power State.

        **Get:** Gets the power state.

            *Returns:* ``True``, ``False``

            *Return type:* `bool`

        **Set:** Sets the power state.

            *Accepted values:``True``, ``False``

            *Value type:* `bool`
        """
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
            else:
                logging.error('Unable to get TV\'s mac address')

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

    def close(self):
        raise NotImplementedError
