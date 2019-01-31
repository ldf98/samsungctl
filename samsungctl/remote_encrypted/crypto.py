from __future__ import print_function
from Crypto.Cipher import AES
import hashlib
from . import keys
import struct
from  .py3rijndael.rijndael import Rijndael
import logging
from binascii import unhexlify as uh,hexlify as he
logger = logging.getLogger('samsungctl')

BLOCK_SIZE = 16
SHA_DIGEST_LENGTH = 20

def bytes2str(data):
    if isinstance(data,str)::
        return data
    else:
        return "".join(chr(x) for x in data)

def EncryptParameterDataWithAES(input):
    iv = b"\x00" * BLOCK_SIZE
    output = b""
    for num in range(0,128,16):
        cipher = AES.new(uh(keys.wbKey), AES.MODE_CBC, iv)
        output += cipher.encrypt(input[num:num+16])
    return output


def DecryptParameterDataWithAES(input):
    iv = b"\x00" * BLOCK_SIZE
    output = b""
    for num in range(0,128,16):
        cipher = AES.new(uh(keys.wbKey), AES.MODE_CBC, iv)
        output += cipher.decrypt(input[num:num+16])
    return output


def applySamyGOKeyTransform(input):
    r = Rijndael(uh(keys.transKey))
    return r.encrypt(input)


def generateServerHello(userId, pin):
    sha1 = hashlib.sha1()
    sha1.update(pin.encode('utf-8'))
    pinHash = sha1.digest()
    aes_key = pinHash[:16]
    logger.debug("AES key: "+bytes2str(he(aes_key)))
    iv = b"\x00" * BLOCK_SIZE
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(uh(keys.publicKey))
    logger.debug("AES encrypted: "+ bytes2str(he(encrypted)))
    swapped = EncryptParameterDataWithAES(encrypted)
    logger.debug("AES swapped: "+ bytes2str(he(swapped)))
    data = struct.pack(">I", len(userId)) + userId.encode('utf-8') + swapped
    logger.debug("data buffer: "+bytes2str(he(data)).upper())
    sha1 = hashlib.sha1()
    sha1.update(data)
    dataHash = sha1.digest()
    logger.debug("hash: "+bytes2str(he(dataHash)))
    serverHello = b"\x01\x02" + b"\x00"*5 + struct.pack(">I", len(userId)+132) + data + b"\x00"*5
    return {"serverHello":serverHello, "hash":dataHash, "AES_key":aes_key}

def parseClientHello(clientHello, dataHash, aesKey, gUserId):
    USER_ID_POS = 15
    USER_ID_LEN_POS = 11
    GX_SIZE = 0x80
    data = uh(clientHello)
    firstLen=struct.unpack(">I",data[7:11])[0]
    userIdLen=struct.unpack(">I",data[11:15])[0]
    destLen = userIdLen + 132 + SHA_DIGEST_LENGTH # Always equals firstLen????:)
    thirdLen = userIdLen + 132
    logger.debug("thirdLen: "+str(thirdLen))
    logger.debug("hello: " + bytes2str(he(data)))
    dest = data[USER_ID_LEN_POS:thirdLen+USER_ID_LEN_POS] + dataHash
    logger.debug("dest: "+bytes2str(he(dest)))
    userId=data[USER_ID_POS:userIdLen+USER_ID_POS]
    logger.debug("userId: " + userId.decode('utf-8'))
    pEncWBGx = data[USER_ID_POS+userIdLen:GX_SIZE+USER_ID_POS+userIdLen]
    logger.debug("pEncWBGx: " + bytes2str(he(pEncWBGx)))
    pEncGx = DecryptParameterDataWithAES(pEncWBGx)
    logger.debug("pEncGx: " + bytes2str(he(pEncGx)))
    iv = b"\x00" * BLOCK_SIZE
    cipher = AES.new(aesKey, AES.MODE_CBC, iv)
    pGx = cipher.decrypt(pEncGx)
    logger.debug("pGx: " + bytes2str(he(pGx)))
    bnPGx = int(bytes2str(he(pGx)),16)
    bnPrime = int(keys.prime,16)
    bnPrivateKey = int(keys.privateKey,16)
    secret = hex(pow(bnPGx, bnPrivateKey, bnPrime)).rstrip("L").lstrip("0x")
    secret = ((len(secret)%2)*'0')+secret
    secret = uh(secret)
    logger.debug("secret: " + bytes2str(he(secret)))
    dataHash2 = data[USER_ID_POS+userIdLen+GX_SIZE:USER_ID_POS+userIdLen+GX_SIZE+SHA_DIGEST_LENGTH]
    logger.debug("hash2: " + bytes2str(he(dataHash2)))
    secret2 = userId + secret
    logger.debug("secret2: " + bytes2str(he(secret2)))
    sha1 = hashlib.sha1()
    sha1.update(secret2)
    dataHash3 = sha1.digest()
    logger.debug("hash3: " + bytes2str(he(dataHash3)))
    if dataHash2 != dataHash3:
        logger.debug("Pin error!!!")
        return False
        logger.debug("Pin OK :)\n")
    flagPos = userIdLen + USER_ID_POS + GX_SIZE + SHA_DIGEST_LENGTH
    if ord(data[flagPos:flagPos+1]):
        logger.debug("First flag error!!!")
        return False
    flagPos = userIdLen + USER_ID_POS + GX_SIZE + SHA_DIGEST_LENGTH
    if struct.unpack(">I",data[flagPos+1:flagPos+5])[0]:
        logger.debug("Second flag error!!!")
        return False
    sha1 = hashlib.sha1()
    sha1.update(dest)
    dest_hash = sha1.digest()
    logger.debug("dest_hash: " + bytes2str(he(dest_hash)))
    finalBuffer = userId + gUserId.encode('utf-8') + pGx + uh(keys.publicKey) + secret
    sha1 = hashlib.sha1()
    sha1.update(finalBuffer)
    SKPrime = sha1.digest()
    logger.debug("SKPrime: " + bytes2str(he(SKPrime)))
    sha1 = hashlib.sha1()
    sha1.update(SKPrime+b"\x00")
    SKPrimeHash = sha1.digest()
    logger.debug("SKPrimeHash: " + bytes2str(he(SKPrimeHash)))
    ctx = applySamyGOKeyTransform(SKPrimeHash[:16])
    return {"ctx": ctx, "SKPrime": SKPrime}

def generateServerAcknowledge(SKPrime):
    sha1 = hashlib.sha1()
    sha1.update(SKPrime+b"\x01")
    SKPrimeHash = sha1.digest()
    return "0103000000000000000014"+bytes2str(he(SKPrimeHash)).upper()+"0000000000"

def parseClientAcknowledge(clientAck, SKPrime):
    sha1 = hashlib.sha1()
    sha1.update(SKPrime+b"\x02")
    SKPrimeHash = sha1.digest()
    tmpClientAck = "0104000000000000000014"+bytes2str(he(SKPrimeHash)).upper()+"0000000000"
    return clientAck == tmpClientAck
