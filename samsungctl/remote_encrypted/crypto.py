from __future__ import print_function
import hashlib
import struct
import logging
import binascii
from Crypto.Cipher import AES
from .py3rijndael.rijndael import Rijndael
from . import keys

logger = logging.getLogger('samsungctl')

BLOCK_SIZE = 16
SHA_DIGEST_LENGTH = 20

try:
    unicode = unicode
except NameError:
    unicode = bytes


def bytes2str(data):
    if isinstance(data, unicode):
        return data.decode('utf-8')
    else:
        return data


def debug(label, data):
    logging.debug(label + ": " + bytes2str(binascii.hexlify(data)))


def EncryptParameterDataWithAES(input):
    iv = b"\x00" * BLOCK_SIZE
    output = b""
    for num in range(0, 128, 16):
        cipher = AES.new(binascii.unhexlify(keys.wbKey), AES.MODE_CBC, iv)
        output += cipher.encrypt(input[num:num + 16])
    return output


def DecryptParameterDataWithAES(input):
    iv = b"\x00" * BLOCK_SIZE
    output = b""
    for num in range(0, 128, 16):
        cipher = AES.new(binascii.unhexlify(keys.wbKey), AES.MODE_CBC, iv)
        output += cipher.decrypt(input[num:num + 16])
    return output


def applySamyGOKeyTransform(input):
    r = Rijndael(binascii.unhexlify(keys.transKey))
    return r.encrypt(input)


def generateServerHello(userId, pin):
    sha1 = hashlib.sha1()
    sha1.update(pin.encode('utf-8'))
    pinHash = sha1.digest()
    aes_key = pinHash[:16]
    debug("AES key", aes_key)
    iv = b"\x00" * BLOCK_SIZE
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(binascii.unhexlify(keys.publicKey))
    debug("AES encrypted", encrypted)
    swapped = EncryptParameterDataWithAES(encrypted)
    debug("AES swapped", swapped)
    data = struct.pack(">I", len(userId)) + userId.encode('utf-8') + swapped
    debug("data buffer", data.upper())
    sha1 = hashlib.sha1()
    sha1.update(data)
    dataHash = sha1.digest()
    debug("hash", dataHash)
    serverHello = (
        b"\x01\x02" +
        b"\x00"*5 +
        struct.pack(">I", len(userId) + 132) +
        data +
        b"\x00" * 5
    )
    return {"serverHello": serverHello, "hash": dataHash, "AES_key": aes_key}


def parseClientHello(clientHello, dataHash, aesKey, gUserId):
    USER_ID_POS = 15
    USER_ID_LEN_POS = 11
    GX_SIZE = 0x80
    data = binascii.unhexlify(clientHello)
    firstLen=struct.unpack(">I", data[7:11])[0]
    userIdLen=struct.unpack(">I", data[11:15])[0]
    destLen = userIdLen + 132 + SHA_DIGEST_LENGTH # Always equals firstLen????:)
    thirdLen = userIdLen + 132

    logger.debug("thirdLen: "+str(thirdLen))
    debug("hello", data)

    dest = data[USER_ID_LEN_POS:thirdLen + USER_ID_LEN_POS] + dataHash
    debug("dest", dest)

    userId=data[USER_ID_POS:userIdLen + USER_ID_POS]
    logger.debug("userId: " + userId.decode('utf-8'))

    pEncWBGx = data[USER_ID_POS + userIdLen:GX_SIZE + USER_ID_POS + userIdLen]
    debug("pEncWBGx", pEncWBGx)

    pEncGx = DecryptParameterDataWithAES(pEncWBGx)
    debug("pEncGx", pEncGx)

    iv = b"\x00" * BLOCK_SIZE
    cipher = AES.new(aesKey, AES.MODE_CBC, iv)
    pGx = cipher.decrypt(pEncGx)
    debug("pGx", pGx)

    bnPGx = int(bytes2str(binascii.hexlify(pGx)), 16)
    bnPrime = int(keys.prime, 16)
    bnPrivateKey = int(keys.privateKey, 16)
    secret = hex(pow(bnPGx, bnPrivateKey, bnPrime)).rstrip("L").lstrip("0x")
    secret = ((len(secret) % 2) * '0') + secret
    secret = binascii.unhexlify(secret)
    debug("secret", secret)

    start = USER_ID_POS + userIdLen + GX_SIZE
    stop = USER_ID_POS + userIdLen + GX_SIZE + SHA_DIGEST_LENGTH

    dataHash2 = data[start:stop]
    debug("hash2",dataHash2)

    secret2 = userId + secret
    debug("secret2", secret2)

    sha1 = hashlib.sha1()
    sha1.update(secret2)
    dataHash3 = sha1.digest()
    debug("hash3", dataHash3)

    if dataHash2 != dataHash3:
        logger.debug("Pin error!!!")
        return False
        # logger.debug("Pin OK :)\n")

    flagPos = userIdLen + USER_ID_POS + GX_SIZE + SHA_DIGEST_LENGTH
    if ord(data[flagPos:flagPos + 1]):
        logger.debug("First flag error!!!")
        return False

    flagPos = userIdLen + USER_ID_POS + GX_SIZE + SHA_DIGEST_LENGTH
    if struct.unpack(">I", data[flagPos + 1:flagPos + 5])[0]:
        logger.debug("Second flag error!!!")
        return False

    sha1 = hashlib.sha1()
    sha1.update(dest)
    dest_hash = sha1.digest()
    debug("dest_hash", dest_hash)

    finalBuffer = (
        userId +
        gUserId.encode('utf-8') +
        pGx +
        binascii.unhexlify(keys.publicKey) +
        secret
    )

    sha1 = hashlib.sha1()
    sha1.update(finalBuffer)
    SKPrime = sha1.digest()
    debug("SKPrime", SKPrime)

    sha1 = hashlib.sha1()
    sha1.update(SKPrime + b"\x00")
    SKPrimeHash = sha1.digest()
    debug("SKPrimeHash", SKPrimeHash)

    ctx = applySamyGOKeyTransform(SKPrimeHash[:16])
    return {"ctx": ctx, "SKPrime": SKPrime}


def generateServerAcknowledge(SKPrime):
    sha1 = hashlib.sha1()
    sha1.update(SKPrime + b"\x01")
    SKPrimeHash = sha1.digest()
    return (
        "0103000000000000000014" +
        bytes2str(binascii.hexlify(SKPrimeHash)).upper()+
        "0000000000"
    )


def parseClientAcknowledge(clientAck, SKPrime):
    sha1 = hashlib.sha1()
    sha1.update(SKPrime + b"\x02")
    SKPrimeHash = sha1.digest()
    tmpClientAck = (
        "0104000000000000000014" +
        bytes2str(binascii.hexlify(SKPrimeHash)).upper() +
        "0000000000"
    )

    return clientAck == tmpClientAck
