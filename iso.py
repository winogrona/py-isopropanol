import abstract_telegram

from enum import IntEnum
from io import BytesIO
from dataclasses import dataclass, field
from typing import Literal, Union, Iterable, SupportsBytes, SupportsIndex
from typing_extensions import Buffer
from abc import abstractmethod

ADDR_LEN = 2
PTYPE_LEN = 1
ISO_BYTEORDER: Literal["little"] = "little" # Doesn't matter at all but still

class PType(IntEnum):
    OPEN = 0
    CLOSE = 1
    KEEPALIVE = 2
    DATA = 3

    @staticmethod
    def from_bytes(
        data: Iterable[SupportsIndex] | SupportsBytes | Buffer,
        byteorder: Literal["little", "big"] = ISO_BYTEORDER,
        signed: bool = False
    ) -> "PType":
        return PType(int.from_bytes(data, signed=False, byteorder=ISO_BYTEORDER))
    
    def to_bytes(
        self, 
        length: SupportsIndex = ADDR_LEN, 
        byteorder: Literal['little', 'big'] = ISO_BYTEORDER, 
        signed: bool = False
    ) -> bytes:
        return int(self).to_bytes(PTYPE_LEN, byteorder=ISO_BYTEORDER, signed=False)

class PeerAddr(int):
    def __init__(self, value: int) -> None:
        try:
            value.to_bytes(ADDR_LEN, signed=False, byteorder=ISO_BYTEORDER)
        except OverflowError:
            raise ValueError("Addresses must fit in %d bytes" % ADDR_LEN)

    @staticmethod
    def from_bytes(
        data: Iterable[SupportsIndex] | SupportsBytes | Buffer,
        byteorder: Literal["little", "big"] = ISO_BYTEORDER,
        signed: bool = False
    ) -> "PeerAddr":
        return PeerAddr(int.from_bytes(data, byteorder=byteorder, signed=signed))

    def to_bytes(
        self, 
        length: SupportsIndex = ADDR_LEN, 
        byteorder: Literal['little', 'big'] = ISO_BYTEORDER, 
        signed: bool = False
    ) -> bytes:
        return super().to_bytes(length, byteorder=byteorder, signed=signed)
        

@dataclass
class Packet:
    saddr: PeerAddr
    daddr: PeerAddr
    ptype: PType
    payload: bytes

    @staticmethod
    def from_bytes(data: bytes) -> "Packet":
        stream = BytesIO(data)

        saddr = PeerAddr.from_bytes(stream.read(ADDR_LEN))
        daddr = PeerAddr.from_bytes(stream.read(ADDR_LEN))
        ptype = PType(PType.from_bytes(stream.read(PTYPE_LEN)))
        payload = stream.read()

        return Packet(
            saddr,
            daddr,
            ptype,
            payload
        )
    
    def to_bytes(self) -> bytes:
        stream = BytesIO()

        stream.write(self.saddr.to_bytes())
        stream.write(self.daddr.to_bytes())
        stream.write(self.ptype.to_bytes())
        stream.write(self.payload)

        return stream.getvalue()

class PacketCodec:
    @abstractmethod
    def encode(self, source: bytes) -> bytes:
        pass

    @abstractmethod
    def decode(self, source: bytes) -> bytes:
        pass

class PlainCodec(PacketCodec):
    def encode(self, source: bytes) -> bytes:
        return source

    def decode(self, source: bytes) -> bytes:
        return source

@dataclass
class Server:
    channel_id: int
    codec: PacketCodec = field(default_factory=PlainCodec)