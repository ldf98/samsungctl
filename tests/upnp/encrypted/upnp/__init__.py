# -*- coding: utf-8 -*-
from __future__ import print_function
import flask
import socket
import struct
import sys
import os
import unittest
import threading

from . import ssdp

IPV4_MCAST_GRP = '239.255.255.250'
IPV6_MCAST_GRP = '[ff02::c]'

BIND_ADDREESS = ('localhost', 1900)

'''
M-SEARCH * HTTP/1.1
ST: ssdp:all
MAN: "ssdp:discover"
HOST: 239.255.255.250:1900
MX: 10
Content-Length: 0


Received 1/22/2019 at 8:03:06 AM (40)

M-SEARCH * HTTP/1.1
ST: upnp:rootdevice
MAN: "ssdp:discover"
HOST: [ff02::c]:1900
MX: 10
Content-Length: 0


'''
BASE_PATH = os.path.abspath(os.path.dirname(__file__))
LOCAL_IP = socket.gethostbyname(socket.gethostname())
UPNP_PORT = 7272


def convert_packet(packet):
    packet_type, packet = packet.decode('utf-8').split('\n', 1)
    packet_type = packet_type.upper().split('*')[0].strip()

    packet = dict(
        (
            line.split(':', 1)[0].strip().upper(),
            line.split(':', 1)[1].strip()
        ) for line in packet.split('\n') if line.strip()
    )

    packet['TYPE'] = packet_type
    return packet


class EncryptedUPNPTest(unittest.TestCase):

    def setUp(self):
        self.app = app = flask.Flask('Encrypted XML Provider')

        def get_file(path):
            path = os.path.join(BASE_PATH, path)
            with open(path, 'r') as f:
                return f.read()

        @app.route('/smp_2_')
        def smp_2_():
            return get_file('smp_2_.xml')

        @app.route('/smp_7_')
        def smp_7_():
            return get_file('smp_7_.xml')

        @app.route('/smp_15_')
        def smp_15_():
            return get_file('smp_15_.xml')

        @app.route('/smp_25_')
        def smp_25_():
            return get_file('smp_25_.xml')

        @app.route('/smp_2_/smp_3_')
        def smp_3_():
            return get_file('smp_2_/smp_3_.xml')

        @app.route('/smp_7_/smp_8_')
        def smp_8_():
            return get_file('smp_7_/smp_8_.xml')

        @app.route('/smp_15_/smp_16_')
        def smp_16_():
            return get_file('smp_15_/smp_16_.xml')

        @app.route('/smp_15_/smp_19_')
        def smp_19_():
            return get_file('smp_15_/smp_19_.xml')

        @app.route('/smp_15_/smp_22_')
        def smp_22_():
            return get_file('smp_15_/smp_22_.xml')

        @app.route('/smp_25_/smp_26_')
        def smp_26_():
            return get_file('smp_25_/smp_26_.xml')

        @app.route('/smp_2_/smp_4_', methods=['POST'])
        def smp_4_():
            '''smp_3_'''
            pass

        @app.route('/smp_7_/smp_9_', methods=['POST'])
        def smp_9_():
            '''smp_8_'''
            pass

        @app.route('/smp_15_/smp_17_', methods=['POST'])
        def smp_17_():
            '''smp_16_'''
            pass

        @app.route('/smp_15_/smp_20_', methods=['POST'])
        def smp_20_():
            '''smp_19_'''
            pass

        @app.route('/smp_15_/smp_23_', methods=['POST'])
        def smp_23_():
            '''smp_22_'''
            pass

        @app.route('/smp_25_/smp_27_', methods=['POST'])
        def smp_27_():
            '''smp_26_'''
            pass

        self.ssdp_event = threading.Event()
        self.sock = sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(BIND_ADDREESS)
        group = socket.inet_aton(IPV4_MCAST_GRP)
        group_membership = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            group_membership
        )

        def ssdp_do():
            while not self.ssdp_event.isSet():
                try:
                    data, address = sock.recvfrom(1024)
                except socket.error:
                    break

                if not data:
                    continue

                packet = convert_packet(data)

                if packet['TYPE'] != 'M-SEARCH':
                    continue

                if (
                    'MAN' in packet and
                    'ST' in packet and
                    packet['MAN'] == '"ssdp:discover"' and
                    packet['ST'] in ('ssdp:all', 'upnp:rootdevice')
                ):
                    for ssdp_packet in ssdp.PACKETS:
                        sock.sendto(
                            ssdp_packet.format(LOCAL_IP, UPNP_PORT),
                            address
                        )

                sock.sendto('ack', address)

        def flask_do():
            app.run(host='0.0.0.0', port=UPNP_PORT)

        self.flask_thread = threading.Thread(target=flask_do, name='flask_server')
        self.flask_thread.start()
        self.ssdp_thread = threading.Thread(target=ssdp_do, name='ssdp_listen')
        self.ssdp_thread.start()

    def tearDown(self):
        self.ssdp_event.set()
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        self.thread.join(3.0)







