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
import requests
import time
import websocket
import json
from lxml import etree
from binascii import hexlify as he
import logging
import traceback

# if sys.version_info[0] < 3:
    # raise ImportError
    
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
        websocket_base.WebSocketBase.__init__(self, config)
        self.url = URL(config)
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

    @LogIt
    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def get_pin(self):
        tv_pin = input("Please enter pin from tv: ")
        return tv_pin

    @LogItWithReturn
    def open(self):
        power = self.power
        paired = self.config.paired

        if self.ctx is None:
            if not power:
                self.power = True

            if not self.power:
                raise RuntimeError('Unable to pair with TV.')

            self.last_request_id = 0

            if self.check_pin_page():
                logger.debug("Pin NOT on TV")
                self.show_pin_page()
            else:
                logger.debug("Pin ON TV")

            while self.ctx is None:
                tv_pin = self.get_pin()

                logger.info("Got pin: '{0}'".format(tv_pin))

                self.first_step_of_pairing()
                output = self.hello_exchange(tv_pin)
                if output:
                    self.ctx = crypto.bytes2str(he(output['ctx']))
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

        if not paired and not power:
            self.power = False
            return False

        return True

    @LogIt
    def show_pin_page(self):
        requests.post(self.url.cloud_pin_page, "pin4")

    @LogItWithReturn
    def check_pin_page(self):
        # <?xml version="1.0" encoding="UTF-8"?>
        # <service xmlns="urn:dial-multiscreen-org:schemas:dial" xmlns:atom="http://www.w3.org/2005/Atom">
        #     <name>CloudPINPage</name>
        #     <options allowStop="true"/>
        #     <state>running</state>
        #     <atom:link rel="run" href="run"/>
        # </service>

        response = requests.get(self.url.cloud_pin_page, timeout=3)

        root = etree.fromstring(response.content)
        root = strip_xmlns(root)

        try:
            state = root.find('state')
            logger.debug("Current state: " + state.text)
            if state.text == 'stopped':
                return True
        except:
            pass

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
                GeneratorServerHello=crypto.bytes2str(he(hello_output['serverHello'])).upper()
            )
        )

        response = requests.post(self.url.step2, json=content)

        # {
        #   "auth_data": {
        #       "auth_type":"SPC",
        #       "request_id":"1",
        #       "GeneratorClientHello":"010100000000000000009E00000006363534333231081C35EB8DB247EB574DAB5FC569464739E34CC3D57892D5436A8D3A288F10645368E76CE0FAF609C302F6B488D5CA00CE7E22825D32C8DCE40AD1EE62DBCD90513972F38BB87A7BDD574EEE679661D117A9513189754142A421805840F2C3247C0F940A4B981C7348211CB422045A9DDCDB2F37FCF0D854701E5FD9B0F55BE94855E546C87859BAAF8825ECD0447A7AC506CC160000000000"
        #   }
        # }

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

        # {
        #   "auth_data":"{
        #       "auth_type":"SPC",
        #       "request_id":"1",
        #       "ClientAckMsg":"0104000000000000000014CEA0857A91E9B9511CC1453433CE79BE222FF32A0000000000",
        #       "session_id":"1"
        #   }
        # }

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

    @LogItWithReturn
    def control(self, key):
        if self.sock is None:
            if not self.config.paired:
                self.open()
                if not self.power:
                    return False
            elif self.power:
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
