from .rijndael import Rijndael
import binascii

_trans_key = '6c9474469ddf7578f3e5ad8a4c703d99'
RIJNDAEL_CIPHER = Rijndael(binascii.unhexlify(_trans_key))

__all__ = ('RIJNDAEL_CIPHER',)
