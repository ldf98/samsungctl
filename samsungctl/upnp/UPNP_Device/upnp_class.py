# -*- coding: utf-8 -*-

import requests
import os
from lxml import etree
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse


try:
    from .xmlns import strip_xmlns
    from .service import Service
    from .embedded_device import EmbeddedDevice
    from .instance_singleton import InstanceSingleton
except ImportError:
    from xmlns import strip_xmlns
    from service import Service
    from embedded_device import EmbeddedDevice
    from instance_singleton import InstanceSingleton


class UPNPObject(object):

    def __init__(self, ip, locations, dump=''):
        self.ip_address = ip
        self._devices = {}
        self._services = {}
        for location in locations:
            parsed_url = urlparse(location)
            url = parsed_url.scheme + '://' + parsed_url.netloc
            response = requests.get(location)

            content = response.content.decode('utf-8')

            if dump:
                path = location
                if path.startswith('/'):
                    path = path[1:]

                if '/' in path:
                    path, file_name = path.rsplit('/', 1)
                    path = os.path.join(dump, path)
                else:
                    file_name = path
                    path = dump

                if not os.path.exists(path):
                    os.makedirs(path)

                if not file_name.endswith('.xml'):
                    file_name += '.xml'

                with open(os.path.join(path, file_name), 'w') as f:
                    f.write(content)

            try:
                root = etree.fromstring(content)
            except etree.XMLSyntaxError:
                continue

            root = strip_xmlns(root)
            node = root.find('device')

            services = node.find('serviceList')
            if services is None:
                services = []

            devices = node.find('deviceList')
            if devices is None:
                devices = []

            for service in services:
                scpdurl = service.find('SCPDURL').text.replace(url, '')

                control_url = service.find('controlURL').text
                if control_url is None:
                    if scpdurl.endswith('.xml'):
                        control_url = scpdurl.rsplit('/', 1)[0]
                        if control_url == scpdurl:
                            control_url = ''
                    else:
                        control_url = scpdurl
                else:
                    control_url = control_url.replace(url, '')

                service_id = service.find('serviceId').text
                service_type = service.find('serviceType').text

                service = Service(
                    self,
                    url,
                    scpdurl,
                    service_type,
                    control_url,
                    node,
                    dump=dump
                )
                name = service_id.split(':')[-1]
                service.__name__ = name
                self._services[name] = service

            for device in devices:
                device = EmbeddedDevice(
                    url,
                    node=device,
                    parent=self,
                    dump=dump
                )
                self._devices[device.__name__] = device

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        if item in self._devices:
            return self._devices[item]

        if item in self._services:
            return self._services[item]

        if item in self.__class__.__dict__:
            if hasattr(self.__class__.__dict__[item], 'fget'):
                return self.__class__.__dict__[item].fget(self)

        raise AttributeError(item)

    @property
    def as_dict(self):
        res = dict(
            services=list(service.as_dict for service in self.services),
            devices=list(device.as_dict for device in self.devices)
        )
        return res

    @property
    def access_point(self):
        return self.__class__.__name__

    @property
    def services(self):
        return list(self._services.values())[:]

    @property
    def devices(self):
        return list(self._devices.values())[:]

    def __str__(self):
        output = '\n\n' + str(self.__name__) + '\n'
        output += 'IP Address: ' + self.ip_address + '\n'
        output += '==============================================\n'

        if self.services:
            output += 'Services:\n'
            for cls in self.services:
                output += cls.__str__(indent='    ').rstrip() + '\n'
        else:
            output += 'Services: None\n'

        if self.devices:
            output += 'Devices:\n'
            for cls in self.devices:
                output += cls.__str__(indent='    ').rstrip() + '\n'
        else:
            output += 'Devices: None\n'

        return output
