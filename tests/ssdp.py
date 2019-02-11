# -*- coding: utf-8 -*-

PACKET_SMP_25 = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:068e7781-006e-1000-bbbf-f877b8a47bf1::upnp:rootdevice\r
Server: SHP, UPnP/1.0, Samsung UPnP SDK/1.0\r
Ext: \r
Location: http://{ip}:{port}/smp_25_\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''

PACKET_SMP_15 = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:068e7781-006e-1000-bbbf-f877b8a47bf1::upnp:rootdevice\r
Server: SHP, UPnP/1.0, Samsung UPnP SDK/1.0\r
Ext: \r
Location: http://{ip}:{port}/smp_15_\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''

PACKET_SMP_7 = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:068e7781-006e-1000-bbbf-f877b8a47bf1::upnp:rootdevice\r
Server: SHP, UPnP/1.0, Samsung UPnP SDK/1.0\r
Ext: \r
Location: http://{ip}:{port}/smp_7_\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''

PACKET_SMP_2 = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:068e7781-006e-1000-bbbf-f877b8a47bf1::upnp:rootdevice\r
Server: SHP, UPnP/1.0, Samsung UPnP SDK/1.0\r
Ext: \r
Location: http://{ip}:{port}/smp_2_\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''

ENCRYPTED_PACKETS = [
    PACKET_SMP_25,
    PACKET_SMP_15,
    PACKET_SMP_7,
    PACKET_SMP_2
]


PACKET_DMR = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:2c782d5f-9fd1-9152-41e1-0af79c23d484::upnp:rootdevice\r
Server: Linux/9.0 UPnP/1.0 PROTOTYPE/1.0\r
Ext: \r
Location: http://{ip}:{port}/dmr/SamsungMRDesc.xml\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''
PACKET_RCR = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:2c782d5f-9fd1-9152-41e1-0af79c23d484::upnp:rootdevice\r
Server: Linux/9.0 UPnP/1.0 PROTOTYPE/1.0\r
Ext: \r
Location: http://{ip}:{port}/rcr/RemoteControlReceiver.xml\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''
PACKET_MAIN_TV_SERVER = '''\
HTTP/1.1 200 OK\r
Content-Length: 0\r
USN: uuid:2c782d5f-9fd1-9152-41e1-0af79c23d484::upnp:rootdevice\r
Server: Linux/9.0 UPnP/1.0 PROTOTYPE/1.0\r
Ext: \r
Location: http://{ip}:{port}/MainTVServer2/MainTVServer2Desc.xml\r
Cache-Control: max-age=1800\r
Date: Thu, 01 Jan 1970 02:33:09 GMT\r
ST: upnp:rootdevice\r
\r
'''

LEGACY_PACKETS = [
    PACKET_DMR,
    PACKET_RCR,
    PACKET_MAIN_TV_SERVER
]
