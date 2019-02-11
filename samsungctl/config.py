# -*- coding: utf-8 -*-

import os
import socket
import json
import logging
import requests
import uuid
from . import wake_on_lan
from . import exceptions


logger = logging.getLogger('samsungctl')
upnp_logger = logging.getLogger('UPNP_Device')


DEFAULT_CONFIG = dict(
    name='samsungctl',
    description=socket.gethostname(),
    host=None,
    port=None,
    id=None,
    method=None,
    timeout=0,
    token=None,
    device_id=None,
    upnp_locations=None,
    paired=None,
    mac=None
)


class Config(object):
    LOG_OFF = logging.NOTSET
    LOG_CRITICAL = logging.CRITICAL
    LOG_ERROR = logging.ERROR
    LOG_WARNING = logging.WARNING
    LOG_INFO = logging.INFO
    LOG_DEBUG = logging.DEBUG

    def __init__(
        self,
        name='samsungctl',
        description=socket.gethostname(),
        host=None,
        port=None,
        id=None,
        method=None,
        timeout=0,
        token=None,
        device_id=None,
        upnp_locations=None,
        paired=False,
        mac=None,
        **_
    ):

        if host is None:
            raise exceptions.ConfigHostError

        if method is None and port is None:
            try:
                response = requests.get(
                    'http://{0}:8001/api/v2/'.format(host),
                    timeout=2
                )
                response = response.json()['device']
                model = response['modelName']
                if model[5] in ('H', 'J'):
                    model_check = model[5:]
                    while True:
                        if model_check.isdigit():
                            model_check = int(model_check)
                            break
                        model_check = model_check[:-1]
                    if model_check <= 5200:
                        raise RuntimeError(
                            'Model {0} does not have the capability '
                            'of being remotely controlled'.format(model)
                        )
                    method = 'encrypted'
                    port = 8080
                    app_id = '654321'
                    id = "654321"
                    device_id = "7e509404-9d7c-46b4-8f6a-e2a9668ad184"

                else:
                    app_id = ''
                    method = 'websocket'

            except (
                ValueError,
                KeyError,
            ):
                raise RuntimeError('Unknown Config Error')
            except (
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError
            ):
                try:
                    requests.get(
                        'http://{0}:9090'.format(host),
                        timeout=2
                    )
                    method = 'legacy'
                    app_id = ''
                    port = 55000

                except requests.exceptions.ConnectTimeout:
                    raise RuntimeError(
                        'TV needs to be turned on for the automatic discovery '
                        'of the connection settings'
                    )

                except requests.exceptions.ConnectionError:
                    raise RuntimeError(
                        'is the ip address {0} the '
                        'address of the TV?'.format(host)
                    )

        elif method is None:
            if port == 55000:
                app_id = ''
                method = 'legacy'
            elif port in (8001, 8002):
                app_id = ''
                method = 'websocket'
            elif port == 8080:
                app_id = '654321'
                id = "654321"
                device_id = "7e509404-9d7c-46b4-8f6a-e2a9668ad184"
                method = 'encrypted'
            else:
                raise exceptions.ConfigPortError(port)
        elif port is None:
            if method == 'legacy':
                app_id = ''
                port = 55000
            elif method == 'websocket':
                app_id = ''
                if token is None:
                    port = 8001
                else:
                    port = 8002
            elif method == 'encrypted':
                port = 8080
                app_id = '654321'
                id = "654321"
                device_id = "7e509404-9d7c-46b4-8f6a-e2a9668ad184"
            else:
                raise exceptions.ConfigUnknownMethod(method)
        else:
            app_id = ''

        if method is None:
            raise exceptions.ConfigUnknownMethod()

        if method not in ('encrypted', 'websocket', 'legacy'):
            raise exceptions.ConfigUnknownMethod(method)

        if mac is None:
            if port in (8001, 8002, 8080) and mac is None:
                try:
                    response = requests.get(
                        'http://{0}:8001/api/v2/'.format(host),
                        timeout=3
                    )
                    response = response.json()['device']
                    if response['networkType'] == 'wired':
                        mac = wake_on_lan.get_mac_address(host)
                    else:
                        mac = response['wifiMac'].upper()
                except (
                    ValueError,
                    KeyError,
                    requests.HTTPError,
                    requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError
                ):
                    pass
            else:
                mac = wake_on_lan.get_mac_address(host)

        if mac is None and port != 55000:
            logger.error('Unable to acquire TV\'s mac address')

        if paired is None:
            if token is not None:
                paired = True
            else:
                paired = False

        if method == 'legacy' and id is None:
            id = str(uuid.uuid4())[1:-1]

        self.name = name
        self.description = description
        self.host = host
        self.port = port
        self.id = id
        self.method = method
        self.timeout = timeout
        self.token = token
        self.path = None
        self.device_id = device_id
        self.upnp_locations = upnp_locations
        self.app_id = app_id

        self.paired = paired
        self.mac = mac

    @property
    def log_level(self):
        return logger.getEffectiveLevel()

    @log_level.setter
    def log_level(self, log_level):
        if log_level is None or log_level == logging.NOTSET:
            logging.basicConfig(format="%(message)s", level=None)
        else:
            logging.basicConfig(format="%(message)s", level=log_level)
            logger.setLevel(log_level)
            upnp_logger.setLevel(log_level)

    def __eq__(self, other):
        if isinstance(other, Config):
            return (
                self.name == other.name and
                self.description == other.description and
                self.port == other.port and
                self.token == other.token and
                self.device_id == other.device_id
            )

        return False

    def __call__(self, **_):
        return self

    def get_pin(self):
        tv_pin = input("Please enter pin from tv: ")
        return tv_pin

    @staticmethod
    def load(path):
        if '~' in path:
            path.replace('~', os.path.expanduser('~'))
        if '%' in path:
            path = os.path.expandvars(path)

        if os.path.isfile(path):
            config = dict(
                list(item for item in DEFAULT_CONFIG.items())
            )
            with open(path, 'r') as f:
                loaded_config = f.read()

                try:
                    loaded_config = json.loads(loaded_config)
                    config.update(loaded_config)

                except ValueError:
                    for line in loaded_config.split('\n'):
                        if not line.strip():
                            continue

                        try:
                            key, value = line.split('=', 1)
                        except ValueError:
                            if line.count('=') == 1:
                                key = line.replace('=', '')
                                value = ''
                            else:
                                continue

                        key = key.lower().strip()

                        if key not in config:
                            continue

                        value = value.strip()

                        if value.lower() in ('none', 'null'):
                            value = None
                        elif not value:
                            value = None
                        elif key in ('port', 'timeout'):
                            try:
                                value = int(value)
                            except ValueError:
                                value = 0
                        elif key == 'upnp_locations':

                            if value.startswith('['):
                                value = value.replace("'", '').replace('"', '')
                                value = value[1:-1]

                            value = list(
                                val.strip() for val in value.split(',')
                                if val.strip()
                            )

                        config[key] = value

            self = Config(**config)
            self.path = path
            return self

        else:
            pth = path

            def wrapper(
                name='samsungctl',
                description=socket.gethostname(),
                host=None,
                port=None,
                id=None,
                method=None,
                timeout=0,
                token=None,
                device_id=None,
                upnp_locations=None,
                paired=False,
                mac=None,
                **_
            ):
                if os.path.isdir(pth):
                    cfg_path = os.path.join(pth, host + '.config')
                    if os.path.exists(cfg_path):
                        return Config.load(cfg_path)
                else:
                    dirs, file_name = os.path.split(pth)

                    if not os.path.exists(dirs):
                        os.makedirs(dirs)

                    cfg_path = pth

                self = Config(
                    name=name,
                    description=description,
                    host=host,
                    port=port,
                    id=id,
                    method=method,
                    timeout=timeout,
                    token=token,
                    device_id=device_id,
                    upnp_locations=upnp_locations,
                    paired=paired,
                    mac=mac
                )
                self.path = cfg_path

                return self
        return wrapper

    def save(self, path=None):
        if path is None:
            if self.path is None:
                raise exceptions.ConfigSavePathNotSpecified
            path = self.path

        elif self.path is None:
            self.path = path

        if not os.path.exists(path):
            path, file_name = os.path.split(path)

            if not os.path.exists(path) or not os.path.isdir(path):
                raise exceptions.ConfigSavePathError(path)

            path = os.path.join(path, file_name)

        if os.path.isdir(path):
            path = os.path.join(path, self.name + '.config')

        if os.path.exists(path):
            with open(path, 'r') as f:
                data = f.read().split('\n')
        else:
            data = []

        new = str(self).split('\n')

        for new_line in new:
            key = new_line.split('=')[0]
            for i, old_line in enumerate(data):
                if old_line.lower().strip().startswith(key):

                    data[i] = new_line
                    break
            else:
                data += [new_line]

        try:
            with open(path, 'w') as f:
                f.write('\n'.join(data))

        except (IOError, OSError):
            import traceback
            traceback.print_exc()
            raise exceptions.ConfigSaveError

    def __iter__(self):
        yield 'name', self.name
        yield 'description', self.description
        yield 'host', self.host
        yield 'port', self.port
        yield 'id', self.id
        yield 'method', self.method
        yield 'timeout', self.timeout
        yield 'token', self.token
        yield 'device_id', self.device_id
        yield 'upnp_locations', self.upnp_locations
        yield 'paired', self.paired
        yield 'mac', self.mac

    def __str__(self):
        upnp_locations = self.upnp_locations

        if upnp_locations:
            upnp_locations = ', '.join(upnp_locations)
        else:
            upnp_locations = None

        return TEMPLATE.format(
            name=self.name,
            description=self.description,
            host=self.host,
            port=self.port,
            id=self.id,
            method=self.method,
            timeout=self.timeout,
            token=self.token,
            device_id=self.device_id,
            upnp_locations=upnp_locations,
            paired=self.paired,
            mac=self.mac
        )


TEMPLATE = '''name = {name}
description = {description}
host = {host}
port = {port}
id = {id}
method = {method}
timeout = {timeout}
token = {token}
device_id = {device_id}
upnp_locations = {upnp_locations}
paired = {paired}
mac = {mac}
'''
