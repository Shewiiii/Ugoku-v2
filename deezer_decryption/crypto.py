from deezer_decryption.constants import BLOWFISH_SECRET
from Crypto.Cipher import Blowfish
from hashlib import md5
from typing import Union


def generate_blowfish_key(track_id: Union[int, str]) -> bytes:
    id_md5 = md5(str(track_id).encode()).hexdigest()
    blowfish_key = "".join(
        [
            chr(ord(id_md5[i]) ^ ord(id_md5[i + 16]) ^ ord(BLOWFISH_SECRET[i]))
            for i in range(16)
        ]
    )
    return str.encode(blowfish_key)


def decrypt_chunk(key: bytes, data: bytes) -> bytes:
    return Blowfish.new(
        key, Blowfish.MODE_CBC, b"\x00\x01\x02\x03\x04\x05\x06\x07"
    ).decrypt(data)
