import json
import asyncio
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, cast, overload, Iterable, TypeAlias
from itertools import cycle
from asyncio import Queue, Future
from datetime import datetime, timedelta

JSONAtomic: TypeAlias = dict[str, "JSONAtomic"] | list["JSONAtomic"] | str | int | float | bool | None

@dataclass
class Message:
    text: str
    id: int
    chat_id: int

    @staticmethod
    def from_dict(src: dict[str, Any]) -> "Message":
        return Message(
            text=src["text"],
            id=src["message_id"],
            chat_id=src["chat_id"]
        )


class TelegramError(Exception):
    code: int
    text: str

    def __init__(self, code: int, text: str) -> None:
        self.code = code
        super().__init__(text)


class NetworkError(Exception):
    pass

@dataclass
class BotToken:
    key: str
    last_used: datetime

@dataclass
class QueuedRequest:
    future: Future[JSONAtomic]
    method: str
    args: dict[str, JSONAtomic] 

class BotController:
    tokens: list[BotToken]

    api_host_proto: Literal["http", "https"] = "https"
    api_host = "api.telegram.org"
    api_host_port = 443
    longpoll_timeout_secs = 10
    api_ratelimit_secs = 0.5
    update_offset = 0

    request_queue: Queue[QueuedRequest]

    def __init__(self, tokens: list[str]):
        self.tokens = [BotToken(
            token,
            datetime.now() - timedelta(seconds=self.api_ratelimit_secs)
        ) for token in tokens]
        self.request_queue = Queue()

    @abstractmethod
    async def http_get_json(self, url: str) -> dict[str, JSONAtomic]:
        ...

    def start(self) -> None:
        asyncio.create_task(self.queue_task())

    async def queue_task(self) -> None:
        async def request_task(token: str, request: QueuedRequest) -> None:
            try:
                result = await self.method(token, request.method, **request.args)

            except Exception as e:
                request.future.set_exception(e)
                return
            
            request.future.set_result(result)

        while True:
            request = await self.request_queue.get()
            for token in cycle(self.tokens):
                if datetime.now() - token.last_used > timedelta(seconds=self.api_ratelimit_secs):
                    asyncio.create_task(request_task(token.key, request))
                    token.last_used = datetime.now()
                    break
            
                await asyncio.sleep(0)

    async def method(
        self,
        token: str,
        method_name: str, 
        **kwargs: JSONAtomic
    ) -> dict[str, Any] | list[Any]:
        args_serialized: list[str] = []

        for (key, value) in kwargs.items():
            if type(value) in [dict, list, bool]:
                args_serialized += "%s=%s" % (key, json.dumps(value))

            elif type(value) in [str, int]:
                args_serialized += "%s=%s" % (key, value)

        url = "%s://%s:%s/bot%s/%s?%s" % (
            self.api_host_proto,
            self.api_host,
            self.api_host_port,
            token,
            method_name,
            '&'.join(args_serialized)
        )
        result = await self.http_get_json(url)

        if not result["ok"]:
            raise TelegramError(
                cast(int, result["error_code"]),
                cast(str, result["description"])
            )

        return cast(dict[str, Any] | list[Any], result["result"])
    
    async def queue_request(self, method_name: str, **kwargs: JSONAtomic) -> JSONAtomic:
        request = QueuedRequest(
            future=asyncio.get_running_loop().create_future(),
            method=method_name,
            args=kwargs
        )
        await self.request_queue.put(request)
        return await request.future

    async def send_message(self, text: str, chat_id: int) -> None:
        await self.queue_request("sendMessage", text=text, chat_id=chat_id)

    async def delete_message(self, message: Message) -> None:
        await self.queue_request("deleteMessage", chat_id=message.chat_id, message_id=message.id)

    async def poll_posts(self, chat_id: int) -> list[Message]:
        res = cast(list[dict[str, JSONAtomic]], await self.queue_request(
            "getUpdates",
            timeout=self.longpoll_timeout_secs,
            allowed_updates=["channel_post"],
            offset=self.update_offset
        ))

        if len(res) == 0:
            return []

        result = []
        self.update_offset = cast(int, res[-1]["update_id"])

        for update in res:
            if "text" not in cast(dict[str, JSONAtomic], update["channel_post"]).keys():
                continue

            result.append(Message.from_dict(update["channel_post"]))

        return result