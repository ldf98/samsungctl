# -*- coding: utf-8 -*-
"""
The code for the encrypted websocket connection is a modified version of the
SmartCrypto library that was modified by eclair4151.
I want to thank eclair4151 for writing the code that allows the samsungctl
library to support H and J (2014, 2015) model TV's

https://github.com/eclair4151/SmartCrypto
"""

# TODO: Python 2 compatibility

from __future__ import print_function
import sys
from lxml import etree
import requests
import time
import websocket
import threading
import logging

if sys.version_info[0] < 3:
    raise ImportError

from . import crypto # NOQA
from .command_encryption import AESCipher # NOQA
from .. import wake_on_lan # NOQA
from ..upnp.UPNP_Device.xmlns import strip_xmlns # NOQA
from ..utils import LogIt, LogItWithReturn # NOQA

logger = logging.getLogger('samsungctl')


class RemoteEncrypted(object):

    @LogIt
    def __init__(self, config):

        if config.token:
            self.ctx, self.current_session_id = config.token.rsplit(':', 1)

            try:
                self.current_session_id = int(self.current_session_id)
            except ValueError:
                pass
        else:
            self.ctx = None
            self.current_session_id = None

        self.sk_prime = False
        self.last_request_id = 0
        self.aes_lib = None
        self.sock = None
        self.config = config
        self._running = False
        self._mac_address = None
        self._power_event = threading.Event()
        self._starting = True

    @property
    @LogItWithReturn
    def mac_address(self):
        if self._mac_address is None:
            _mac_address = wake_on_lan.get_mac_address(self.config.host)
            if _mac_address is None:
                _mac_address = ''

            self._mac_address = _mac_address

        return self._mac_address

    @property
    @LogItWithReturn
    def power(self):
        if not self._starting and not self._running and self.config.paired:
            try:
                self.open()
                return True
            except RuntimeError:
                return False

        try:
            requests.get(
                ' http://{0}:8001/api/v2/'.format(self.config.host),
                timeout=2
            )
            return True
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            return False

    @power.setter
    @LogIt
    def power(self, value):
        if not self._starting and not self._running and self.config.paired:
            try:
                self.open()
            except RuntimeError:
                pass

        if value and self.sock is None:
            if self.mac_address:
                count = 0
                wake_on_lan.send_wol(self.mac_address)
                self._power_event.wait(10)

                try:
                    self.open()
                except:
                    while not self._power_event.isSet() and count < 6:
                        wake_on_lan.send_wol(self.mac_address)
                        self._power_event.wait(2)
                        try:
                            self.open()
                            break
                        except:
                            count += 1

                    if count == 6:
                        logger.error(
                            'Unable to power on the TV, '
                            'check network connectivity'
                        )

        elif not value and self.sock is not None:
            count = 0
            while (
                not self._power_event.isSet() and
                self.sock is not None and
                count < 6
            ):
                self.control('KEY_POWER')
                self.control('KEY_POWEROFF')
                self._power_event.wait(2.0)
                count += 1

            if count == 6:
                logger.info('Unable to power off the TV')

    @LogIt
    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    @LogIt
    def open(self):
        self._starting = True
        if self.ctx is None:
            self.start_pairing()
            while self.ctx is None:
                tv_pin = input("Please enter pin from tv: ")

                logger.info("Got pin: '" + tv_pin + "'\n")

                self.first_step_of_pairing()
                output = self.hello_exchange(tv_pin)
                if output:
                    self.ctx = output['ctx'].hex()
                    self.sk_prime = output['SKPrime']
                    logger.debug("ctx: " + self.ctx)
                    logger.info("Pin accepted :)\n")
                else:
                    logger.info("Pin incorrect. Please try again...\n")

            self.current_session_id = self.acknowledge_exchange()
            self.config.token = (
                str(self.ctx) + ':' + str(self.current_session_id)
            )

            logger.info('***************************************')
            logger.info('USE THE FOLLOWING NEXT TIME YOU CONNECT')
            logger.info('***************************************')
            logger.info(
                '--host {0} '
                '--method encryption '
                '--token {1}'.format(self.config.host, self.config.token)
            )

            self.close_pin_page()
            logger.info("Authorization successful :)\n")
            self.config.paired = True

        millis = int(round(time.time() * 1000))
        step4_url = (
            'http://' +
            self.config.host +
            ':8000/socket.io/1/?t=' +
            str(millis)
        )

        if not self.power:
            self.power = True

        try:
            websocket_response = requests.get(step4_url, timeout=3)
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            raise RuntimeError(
                'Unable to open connection.. Is the TV off?!?'
            )

        # websocket_response: Nfzt3klmFoqY1m99wOBH:60:60:websocket,htmlfile,xhr-polling,jsonp-polling

        websocket_url = (
            'ws://' +
            self.config.host +
            ':8000/socket.io/1/websocket/' +
            websocket_response.text.split(':')[0]
        )

        logger.debug(websocket_url)

        self.aes_lib = AESCipher(self.ctx.upper(), self.current_session_id)
        self.sock = websocket.create_connection(websocket_url)
        time.sleep(0.35)
        self._starting = False

    @LogItWithReturn
    def get_full_url(self, url_path):
        return (
            "http://{0}:{1}{2}".format(
                self.config.host,
                self.config.port,
                url_path
            )
        )

    @LogItWithReturn
    def get_request_url(self, step):
        return self.get_full_url(
            "/ws/pairing?step=" +
            str(step) +
            "&app_id=" +
            self.config.app_id +
            "&device_id=" +
            self.config.device_id
        )

    @LogIt
    def show_pin_page(self):
        requests.post(self.get_full_url("/ws/apps/CloudPINPage"), "pin4")

    @LogItWithReturn
    def check_pin_page(self):
        full_url = self.get_full_url("/ws/apps/CloudPINPage")
        # <?xml version="1.0" encoding="UTF-8"?>
        # <service xmlns="urn:dial-multiscreen-org:schemas:dial" xmlns:atom="http://www.w3.org/2005/Atom">
        #     <name>CloudPINPage</name>
        #     <options allowStop="true"/>
        #     <state>running</state>
        #     <atom:link rel="run" href="run"/>
        # </service>

        response = requests.get(full_url, timeout=3)

        root = etree.fromstring(response.content)
        root = strip_xmlns(root)

        try:
            state = root.find('service').find('state')
            logger.debug("Current state: " + state.text)
            if state.text == 'stopped':
                return True
        except:
            pass

        return False

    @LogIt
    def first_step_of_pairing(self):
        first_step_url = self.get_request_url(0)
        first_step_url += "&type=1"
        _ = requests.get(first_step_url).text

    @LogIt
    def start_pairing(self):
        self.last_request_id = 0

        if self.check_pin_page():
            logger.debug("Pin NOT on TV")
            self.show_pin_page()
        else:
            logger.debug("Pin ON TV")

    @LogItWithReturn
    def hello_exchange(self, pin):
        hello_output = crypto.generateServerHello(self.config.id, pin)

        if not hello_output:
            return False

        content = dict(
            auth_data=dict(
                auth_type="SPC",
                GeneratorServerHello=hello_output['serverHello'].hex().upper()
            )
        )

        second_step_url = self.get_request_url(1)
        response = requests.post(second_step_url, json=content)

        # {
        #   "auth_data": {
        #       "auth_type":"SPC",
        #       "request_id":"1",
        #       "GeneratorClientHello":"010100000000000000009E00000006363534333231081C35EB8DB247EB574DAB5FC569464739E34CC3D57892D5436A8D3A288F10645368E76CE0FAF609C302F6B488D5CA00CE7E22825D32C8DCE40AD1EE62DBCD90513972F38BB87A7BDD574EEE679661D117A9513189754142A421805840F2C3247C0F940A4B981C7348211CB422045A9DDCDB2F37FCF0D854701E5FD9B0F55BE94855E546C87859BAAF8825ECD0447A7AC506CC160000000000"
        #   }
        # }

        logger.debug('second_step_response:', response.content)

        try:
            auth_data = response.json()['auth_data']
            client_hello = auth_data['GeneratorClientHello']
            request_id = auth_data['request_id']
        except (ValueError, KeyError):
            return {}

        self.last_request_id = int(request_id)

        return crypto.parseClientHello(
            client_hello,
            hello_output['hash'],
            hello_output['AES_key'],
            self.config.id
        )

    @LogItWithReturn
    def acknowledge_exchange(self):
        server_ack_message = crypto.generateServerAcknowledge(self.sk_prime)

        content = dict(
            auth_data=dict(
                auth_type="SPC",
                request_id=str(self.last_request_id),
                ServerAckMsg=server_ack_message
            )
        )

        third_step_url = self.get_request_url(2)
        response = requests.post(third_step_url, json=content)

        # {
        #   "auth_data":"{
        #       "auth_type":"SPC",
        #       "request_id":"1",
        #       "ClientAckMsg":"0104000000000000000014CEA0857A91E9B9511CC1453433CE79BE222FF32A0000000000",
        #       "session_id":"1"
        #   }
        # }

        if "secure-mode" in response.content:
            raise RuntimeError(
                "TODO: Implement handling of encryption flag!!!!"
            )

        try:
            auth_data = response.json()['auth_data']
            client_ack = auth_data['ClientAckMsg']
            session_id = auth_data['session_id']
        except (ValueError, KeyError):
            raise RuntimeError(
                "Unable to get session_id and/or ClientAckMsg!!!"
            )

        logger.debug("session_id: " + session_id)

        if not crypto.parseClientAcknowledge(client_ack, self.sk_prime):
            raise RuntimeError("Parse client ack message failed.")

        return session_id

    @LogIt
    def close_pin_page(self):
        full_url = self.get_full_url("/ws/apps/CloudPINPage/run")
        requests.delete(full_url)
        return False

    @LogIt
    def control(self, key):
        if self.sock is None:
            if not self._running:
                self.open()
            else:
                logger.info('Is thee TV on?!?')
                return
        try:

            # need sleeps cuz if you send commands to quick it fails
            self.sock.send('1::/com.samsung.companion')
            # pairs to this app with this command.
            time.sleep(0.35)

            self.sock.send(self.aes_lib.generate_command(key))
            time.sleep(0.35)
            return True
        except:
            self.sock = None
            return False
