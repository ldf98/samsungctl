from Crypto.Cipher import AES as _AES
import binascii
from .keys import wbKey, transKey

from .rijndael import Rijndael


# Padding for the input string --not
# related to encryption itself.
BLOCK_SIZE = 16  # Bytes
IV = b'\x00' * BLOCK_SIZE


MODE_CBC = _AES.MODE_CBC


def pad(s):
    return (
        s +
        (BLOCK_SIZE - len(s) % BLOCK_SIZE) *
        chr(BLOCK_SIZE - len(s) % BLOCK_SIZE)
    )


def unpad(s):
    return s[:-ord(s[len(s) - 1:])]


class AES:
    """
    Usage:
        c = AESCipher('password').encrypt('message')
        m = AESCipher('password').decrypt(c)
    Tested under Python 3 and PyCrypto 2.6.1.
    """

    def __init__(self, key, mode=_AES.MODE_ECB, *args):
        self.key = binascii.unhexlify(key)
        if mode == MODE_CBC:
            self._cipher = _AES.new(self.key, mode, IV)
        else:
            self._cipher = _AES.new(self.key, mode, *args)

    def decrypt(self, enc, remove_padding=True):
        if remove_padding:
            return unpad(self._cipher.decrypt(binascii.unhexlify(enc)))
        else:
            return self._cipher.decrypt(binascii.unhexlify(enc))

    def encrypt(self, raw, add_padding=True):
        if add_padding:
            return self._cipher.encrypt(pad(raw).encode("utf8"))
        else:
            return self._cipher.encrypt(raw.encode("utf8"))


AES_CIPHER = AES(wbKey, MODE_CBC)
