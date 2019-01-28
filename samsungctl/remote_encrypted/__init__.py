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
import json
import re
import requests
import time
import websocket
import logging

if sys.version_info[0] < 3:
    raise ImportError

from . import crypto # NOQA
from .command_encryption import AESCipher # NOQA
from .. import websocket_base # NOQA
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

    @LogItWithReturn
    @property
    def request(self):
        return "{0}/ws/pairing?step={{0}}&app_id={1}&device_id={2}".format(
            self.full_url,
            self.config.app_id,
            self.config.device_id
        )

    @LogItWithReturn
    @property
    def step1(self):
        return self.request.format(0) + "&type=1"

    @LogItWithReturn
    @property
    def step2(self):
        return self.request.format(1)

    @LogItWithReturn
    @property
    def step3(self):
        return self.request.format(2)

    @LogItWithReturn
    @property
    def step4(self):
        millis = int(round(time.time() * 1000))
        return '{0}:8000/socket.io/1/?t={1}'.format(self.base_url, millis)

    @LogItWithReturn
    @property
    def websocket(self):
        try:
            websocket_response = requests.get(self.step4, timeout=3)
        except (requests.HTTPError, requests.exceptions.ConnectTimeout):
            logger.info(
                'Unable to open connection.. Is the TV on?!?'
            )
            return None

        print('websocket_response: ' + websocket_response.content)

        websocket_url = (
            'ws://{0}:8000/socket.io/1/websocket/{1}'.format(
                self.config.host,
                websocket_response.text.split(':')[0]
            )
        )

        return websocket_url

    @LogItWithReturn
    @property
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

    @LogItWithReturn
    def open(self):
        power = self.power
        paired = self.config.paired

        if self.ctx is None:
            if not power:
                self.power = True

            if not self.power:
                raise RuntimeError('Unable to pair with TV.')

            self.start_pairing()
            while self.ctx is None:
                tv_pin = input("Please enter pin from tv: ")

                logger.info("Got pin: '{0}'".format(tv_pin))

                self.first_step_of_pairing()
                output = self.hello_exchange(tv_pin)
                if output:
                    self.ctx = output['ctx'].hex()
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
        response = requests.post(self.url.cloud_pin_page, "pin4")
        print('show_pin_page: ' + response.content)

    @LogItWithReturn
    def check_pin_page(self):
        page = requests.get(self.url.cloud_pin_page, timeout=3).text
        print('page: ' + page)

        output = re.search('state>([^<>]*)</state>', page, flags=re.IGNORECASE)
        if output is not None:
            state = output.group(1)
            logger.debug("Current state: " + state)
            if state == "stopped":
                return True
        return False

    @LogIt
    def first_step_of_pairing(self):
        response = requests.get(self.url.step1).text
        print('first_step_of_pairing:', response)

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
            return {}

        content = dict(
            auth_Data=dict(
                auth_type='SPC',
                GeneratorServerHello=hello_output['serverHello'].hex().upper()
            )
        )

        second_step = requests.post(self.url.step2, json.dumps(content)).text

        print('second_step_response:', second_step)
        logger.debug('second_step_response: ' + second_step)

        output = re.search(
            'request_id.*?(\d).*?GeneratorClientHello.*?:.*?(\d[0-9a-zA-Z]*)',
            second_step,
            flags=re.IGNORECASE
        )

        if output is None:
            return {}

        self.last_request_id = int(output.group(1))

        return crypto.parseClientHello(
            output.group(2),
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

        third_step = requests.post(self.url.step3, json.dumps(content)).text

        print('third_step_response:', third_step)

        if "secure-mode" in third_step:
            raise RuntimeError(
                "TODO: Implement handling of encryption flag!!!!"
            )

        output = re.search(
            'ClientAckMsg.*?:.*?(\d[0-9a-zA-Z]*).*?session_id.*?(\d)',
            third_step,
            flags=re.IGNORECASE
        )

        if output is None:
            raise RuntimeError(
                "Unable to get session_id and/or ClientAckMsg!!!"
            )

        client_ack = output.group(1)
        if not crypto.parseClientAcknowledge(client_ack, self.sk_prime):
            raise RuntimeError("Parse client ack message failed.")

        session_id = output.group(2)
        logger.debug("session_id: " + session_id)

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
            self.close()
            return False
