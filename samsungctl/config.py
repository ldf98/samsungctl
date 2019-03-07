# -*- coding: utf-8 -*-

import os
import socket
import json
import logging
import uuid as _uuid
from . import exceptions

logger = logging.getLogger('samsungctl')

LOGGING_FORMAT = '''\
'[%(levelname)s][%(thread)d] %(name)s.%(module)s.%(funcName)s
%(message)s
'''


class Config(object):
    LOG_OFF = logging.NOTSET
    LOG_CRITICAL = logging.CRITICAL
    LOG_ERROR = logging.ERROR
    LOG_WARNING = logging.WARNING
    LOG_INFO = logging.INFO
    LOG_DEBUG = logging.DEBUG

    def __init__(
        self,
        name=None,
        description=socket.gethostname(),
        display_name=None,
        host=None,
        port=None,
        id=None,
        method=None,
        timeout=0,
        token=None,
        # device_id=None,
        upnp_locations=None,
        paired=False,
        mac=None,
        uuid=None,
        model=None,
        app_id=None,
        # user_id=None,
        **_
    ):

        if name is None:
            name = 'Samsung TV Connector [{0}]'.format(socket.gethostname())
        if id is None:
            id = str(_uuid.uuid4())[1:-1]

        self.name = name
        self.description = description
        self.host = host
        self.port = port
        self.method = method
        self.timeout = timeout
        self.token = token
        self.path = None
        # self.device_id = device_id
        self.upnp_locations = upnp_locations
        self.app_id = app_id
        # self.user_id = user_id
        self.uuid = uuid
        self.id = id
        self.paired = paired
        self.model = model
        self.mac = mac
        self._display_name = display_name

    @property
    def display_name(self):
        if self._display_name is None:
            return self.model

        return self._display_name

    @display_name.setter
    def display_name(self, value):
        self._display_name = value

    @property
    def log_level(self):
        return logger.getEffectiveLevel()

    @log_level.setter
    def log_level(self, log_level):
        if log_level is None or log_level == logging.NOTSET:
            logging.basicConfig(format=LOGGING_FORMAT, level=None)
        else:
            logging.basicConfig(format=LOGGING_FORMAT, level=log_level)
            logger.setLevel(log_level)

    def __eq__(self, other):
        if isinstance(other, Config):
            return other.uuid == self.uuid
        return False

    def __call__(self, **_):
        return self

    def get_pin(self):
        tv_pin = input("Please enter pin from tv: ")
        return str(tv_pin)

    def copy(self, src):
        self.host = src.host
        self.upnp_locations = src.upnp_locations
        self.mac = src.mac
        self.app_id = src.app_id
        self.model = src.model

    @staticmethod
    def load(path):
        if '~' in path:
            path.replace('~', os.path.expanduser('~'))
        if '%' in path:
            path = os.path.expandvars(path)

        if os.path.isfile(path):
            config = dict()
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
            logger.debug(str(config))
            self = Config(**config)
            self.path = path

            logger.debug(str(self))
            return self

        else:
            pth = path

            def wrapper(
                name=None,
                description=socket.gethostname(),
                host=None,
                port=None,
                id=None,
                method=None,
                timeout=0,
                token=None,
                upnp_locations=None,
                paired=False,
                mac=None,
                uuid=None,
                app_id=None,
                model=None,
                display_name=None,
                **_
            ):
                if os.path.isdir(pth):
                    cfg_path = os.path.join(pth, uuid + '.config')
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
                    upnp_locations=upnp_locations,
                    paired=paired,
                    mac=mac,
                    uuid=uuid,
                    app_id=app_id,
                    model=model,
                    display_name=display_name
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
            if self.uuid is None:
                return

            path = os.path.join(path, self.uuid + '.config')

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
        yield 'upnp_locations', self.upnp_locations
        yield 'paired', self.paired
        yield 'mac', self.mac
        yield 'uuid', self.uuid
        yield 'app_id', self.app_id
        yield 'model', self.model
        yield 'display_name', self._display_name

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
            upnp_locations=upnp_locations,
            paired=self.paired,
            mac=self.mac,
            model=self.model,
            app_id=self.app_id,
            uuid=self.uuid,
            display_name=self._display_name
        )


TEMPLATE = '''\
name = {name}
description = {description}
host = {host}
port = {port}
id = {id}
method = {method}
timeout = {timeout}
token = {token}
upnp_locations = {upnp_locations}
paired = {paired}
mac = {mac}
model = {model}
app_id = {app_id}
uuid = {uuid}
display_name = {display_name}
'''
