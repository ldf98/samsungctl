# -*- coding: utf-8 -*-
"""
The code for the encrypted websocket connection is a modified version of the
SmartCrypto library that was modified by eclair4151.
I want to thank eclair4151 for writing the code that allows the samsungctl
library to support H and J (2014, 2015) model TV's

https://github.com/eclair4151/SmartCrypto
"""


from __future__ import print_function
import requests
import time
import websocket
import threading
import json
from lxml import etree
import binascii
import logging
import traceback
from .. import wake_on_lan


try:
    input = raw_input
except NameError:
    pass

from . import crypto # NOQA
from .command_encryption import AESCipher # NOQA
from .. import websocket_base # NOQA
from ..upnp.UPNP_Device.xmlns import strip_xmlns # NOQA
from ..utils import LogIt, LogItWithReturn # NOQA

logger = logging.getLogger('samsungctl')


class URL(object):

    def __init__(self, config):
        self.config = config

    @property
    def base_url(self):
        return 'http://{0}'.format(self.config.host)

    @property
    def full_url(self):
        return "{0}:{1}".format(self.base_url, self.config.port)

    @property
    @LogItWithReturn
    def request(self):
        return "{0}/ws/pairing?step={{0}}&app_id={1}&device_id={2}".format(
            self.full_url,
            self.config.app_id,
            self.config.device_id
        )

    @property
    @LogItWithReturn
    def step1(self):
        return self.request.format(0) + "&type=1"

    @property
    @LogItWithReturn
    def step2(self):
        return self.request.format(1)

    @property
    @LogItWithReturn
    def step3(self):
        return self.request.format(2)

    @property
    @LogItWithReturn
    def step4(self):
        millis = int(round(time.time() * 1000))
        return '{0}:8000/socket.io/1/?t={1}'.format(self.base_url, millis)

    @property
    @LogItWithReturn
    def websocket(self):
        try:
            websocket_response = requests.get(self.step4, timeout=3)
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            logger.info(
                'Unable to open connection.. Is the TV on?!?'
            )
            return None

        logger.debug('step 4: ' + websocket_response.content.decode('utf-8'))

        websocket_url = (
            'ws://{0}:8000/socket.io/1/websocket/{1}'.format(
                self.config.host,
                websocket_response.text.split(':')[0]
            )
        )

        return websocket_url

    @property
    @LogItWithReturn
    def cloud_pin_page(self):
        return "{0}/ws/apps/CloudPINPage".format(self.full_url)


class RemoteEncrypted(websocket_base.WebSocketBase):

    @LogIt
    def __init__(self, config):
        self.url = URL(config)

        if config.token:
            self.ctx, self.current_session_id = config.token.rsplit(':', 1)

            try:
                self.current_session_id = int(self.current_session_id)
            except ValueError:
                pass
        else:
            config.set_pin = self.set_pin
            self.ctx = None
            self.current_session_id = None

        self.sk_prime = False
        self.last_request_id = 0
        self.aes_lib = None

        super(RemoteEncrypted, self).__init__(config)

    @LogItWithReturn
    def open(self):
        if self.sock is not None:
            return True

        starting = self._starting

        power = self.power
        paired = self.config.paired

        if not starting:
            self._starting = True
            if not self.config.paired and not power:
                self.power = True

                if not self.power:
                    raise RuntimeError('Unable to pair with TV.')

        self.last_request_id = 0

        if self.ctx is None:

            if self.check_pin_page():
                logger.debug("Pin NOT on TV")
                self.show_pin_page()
            else:
                logger.debug("Pin ON TV")

            while self.ctx is None:
                tv_pin = self.config.get_pin()
                if tv_pin is False:
                    raise RuntimeError('Pin retry limit reached.')
                if tv_pin is None:
                    continue

                logger.info("Got pin: '{0}'".format(tv_pin))

                self.first_step_of_pairing()
                output = self.hello_exchange(tv_pin)
                if output:
                    self.ctx = crypto.bytes2str(
                        binascii.hexlify(output['ctx'])
                    )
                    self.sk_prime = output['SKPrime']
                    logger.debug("ctx: " + self.ctx)
                    logger.info("Pin accepted")
                else:
                    logger.info("Pin incorrect. Please try again...")

            self.current_session_id = self.acknowledge_exchange()
            self.config.token = (
                str(self.ctx) + ':' + str(self.current_session_id)
            )

            self.close_pin_page()
            logger.info("Authorization successful.")
            self.config.paired = True

        websocket_url = self.url.websocket
        if websocket_url is None:
            return False

        logger.debug(websocket_url)

        self.aes_lib = AESCipher(self.ctx.upper(), self.current_session_id)
        self.sock = websocket.create_connection(websocket_url)
        time.sleep(0.35)

        if not self._running:
            self._thread = threading.Thread(target=self.loop)
            self._thread.start()

        if not paired and not power:

            self.power = False
            self.close()
            self._starting = False
            return False

        self._starting = False
        return True

    @LogIt
    def show_pin_page(self):
        requests.post(self.url.cloud_pin_page, "pin4")

    @LogItWithReturn
    def check_pin_page(self):
        response = requests.get(self.url.cloud_pin_page, timeout=3)

        try:
            root = etree.fromstring(response.content)
        except etree.LxmlSyntaxError:
            return False

        root = strip_xmlns(root)

        state = root.find('state')
        if state is not None:
            logger.debug("Current state: " + state.text)
            if state.text == 'stopped':
                return True

        return False

    @LogIt
    def first_step_of_pairing(self):
        response = requests.get(self.url.step1)
        logger.debug('step 1: ' + response.content.decode('utf-8'))

    @LogItWithReturn
    def hello_exchange(self, pin):
        hello_output = crypto.generateServerHello(self.config.id, pin)

        if not hello_output:
            return {}

        content = dict(
            auth_Data=dict(
                auth_type='SPC',
                GeneratorServerHello=crypto.bytes2str(
                    binascii.hexlify(hello_output['serverHello'])
                ).upper()
            )
        )

        response = requests.post(self.url.step2, json=content)
        logger.debug('step 2: ' + response.content.decode('utf-8'))

        try:
            auth_data = json.loads(response.json()['auth_data'])
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
            auth_Data=dict(
                auth_type='SPC',

                request_id=str(self.last_request_id),
                ServerAckMsg=server_ack_message
            )
        )

        response = requests.post(self.url.step3, json=content)
        logger.debug("step 3: " + response.content.decode('utf-8'))

        if "secure-mode" in response.content.decode('utf-8'):
            raise RuntimeError(
                "TODO: Implement handling of encryption flag!!!!"
            )

        try:
            auth_data = json.loads(response.json()['auth_data'])
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
        requests.delete(self.url.cloud_pin_page + '/run')
        return False

    @LogIt
    def power(self, value):
        event = threading.Event()

        if value and not self.power:
            if self.mac_address:
                count = 0
                wake_on_lan.send_wol(self.mac_address)
                event.wait(1.0)

                while not self.power and count < 20:
                    if not self._running:
                        try:
                            self.open()
                        except:
                            pass
                    wake_on_lan.send_wol(self.mac_address)
                    event.wait(1.0)

                    count += 1

                if count == 20:
                    logger.error(
                        'Unable to power on the TV, '
                        'check network connectivity'
                    )
            else:
                logging.error('Unable to get TV\'s mac address')

        elif not value and self.power:
            count = 0
            event = threading.Event()

            self.sock.send('1::/com.samsung.companion')
            time.sleep(0.35)

            self.sock.send(self.aes_lib.generate_command('KEY_POWER'))
            time.sleep(0.35)
            event.wait(2.0)

            self.sock.send('1::/com.samsung.companion')
            time.sleep(0.35)

            self.sock.send(self.aes_lib.generate_command('KEY_POWEROFF'))
            time.sleep(0.35)

            while self.power and count < 10:
                event.wait(1.0)
                count += 1

            if count == 10:
                logger.info('Unable to power off the TV')

    power = property(fget=websocket_base.WebSocketBase.power, fset=power)

    @LogItWithReturn
    def control(self, key):
        if key == 'KEY_POWERON':
            if not self.power:
                self.power = True
            return
        elif key == 'KEY_POWEROFF':
            if self.power:
                self.power = False
            return
        elif key == 'KEY_POWER':
            self.power = not self.power
            return

        elif self.sock is None:
            if not self.config.paired:
                self.open()
            else:
                logger.info('Is the TV on?!?')
                return False
        try:
            self.sock.send('1::/com.samsung.companion')
            time.sleep(0.35)

            self.sock.send(self.aes_lib.generate_command(key))
            time.sleep(0.35)
            return True
        except:
            traceback.print_exc()
            self.close()
            return False
