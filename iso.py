import abstract_telegram
import base65536

import asyncio
from enum import IntEnum
from io import BytesIO
from dataclasses import dataclass, field
from typing import Literal, Union, Iterable, SupportsBytes, SupportsIndex
from typing import Awaitable, Callable, Coroutine
from typing_extensions import Buffer
from abc import abstractmethod
from logging import getLogger
from abstract_telegram import TelegramError

logger = getLogger(__name__)

ADDR_LEN = 2
PTYPE_LEN = 1
ISO_BYTEORDER: Literal["little"] = "little"

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
    payload: bytes

    magic = "xISO"
    header_size = 2 * ADDR_LEN + len(magic.encode("utf8"))

    @staticmethod
    def from_bytes(data: bytes) -> "Packet":
        if len(data) < Packet.header_size:
            raise ValueError("buffer is too small to form a packet")

        stream = BytesIO(data)

        saddr = PeerAddr.from_bytes(stream.read(ADDR_LEN))
        daddr = PeerAddr.from_bytes(stream.read(ADDR_LEN))
        payload = stream.read()

        return Packet(
            saddr,
            daddr,
            payload
        )
    
    def to_bytes(self) -> bytes:
        stream = BytesIO()

        stream.write(self.saddr.to_bytes())
        stream.write(self.daddr.to_bytes())
        stream.write(self.payload)

        return stream.getvalue()

'''Could be used for obfuscation or some kind of encryption'''
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

class Connection:
    pass

@dataclass
class Server:
    channel_id: int
    bot: abstract_telegram.BotController
    codec: PacketCodec = field(default_factory=PlainCodec)
    packet_handler: Callable[[Packet], Coroutine[None, None, None]] | None = None

    SERVER_ADDR = PeerAddr(0)
    BROADCASR_ADDR = PeerAddr(1)
    UNKNOWN_ADDR = PeerAddr(2)

    MESSAGE_START_MAGIC = "ISO["
    MESSAGE_END_MAGIC = "]"

    async def send(self, daddr: PeerAddr, payload: bytes) -> None:
        packet = Packet(saddr=Server.SERVER_ADDR, daddr=daddr, payload=payload)
        raw = "%s%s%s" % (
            Server.MESSAGE_START_MAGIC,
            base65536.encode(self.codec.encode(packet.to_bytes())),
            Server.MESSAGE_END_MAGIC
        )
        await self.bot.send_message(text=raw, chat_id=self.channel_id)

    def start(self) -> None:
        asyncio.create_task(self.listen_task())
        self.bot.start()

    async def listen_task(self) -> None:
        while True:
            logger.info("Polling new posts")
            messages = await self.bot.poll_posts(self.channel_id)
            logger.info("Received polling results: %s" % messages)

            if len(messages) == 0:
                continue

            for message in messages:
                if not message.text.startswith(Server.MESSAGE_START_MAGIC):
                    logger.error("Received message doesn't start with START_MAGIC `%s`" % Server.MESSAGE_START_MAGIC)
                    try:
                        await self.bot.delete_message(message)
                    except TelegramError as e:
                        logger.error("Failed to delete a message: %s" % e)

                    continue
                    
                stripped_text = message.text[len(Server.MESSAGE_START_MAGIC):-len(Server.MESSAGE_END_MAGIC)]
                logger.debug("Stripped message text: `%s`" % stripped_text)

                try:
                    encoded_packet = base65536.decode(stripped_text)

                except ValueError:
                    logger.error("msg_id %d contains a non-base65536 character, deleting it")
                    try:
                        await self.bot.delete_message(message)
                    except TelegramError as e:
                        logger.error("Failed to delete a message: %s" % e)

                    continue

                try:
                    packet = Packet.from_bytes(self.codec.decode(encoded_packet))

                except ValueError as e:
                    logger.error("msg_id %i: packet decoding error: %s" % (message.id, e))
                    await self.bot.delete_message(message)
                    continue

                if packet.daddr == Server.SERVER_ADDR:
                    if self.packet_handler is not None:
                        asyncio.create_task(self.packet_handler(packet))

                    await self.bot.delete_message(message)
                
                elif packet.daddr == Server.BROADCASR_ADDR:
                    logger.error("msg_id %i: received a cool broadcast packet but that's not implemented yet :(")
                    continue

                else:
                    logger.error("msg_id %i: received a cool routable packet but that's not implemented yet :(")
                    continue