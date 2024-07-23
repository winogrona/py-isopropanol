import json
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, cast

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


class Bot:
    token: str

    api_host_proto: Literal["http", "https"] = "https"
    api_host = "api.telegram.org"
    api_host_port = 443
    longpoll_timeout = 10
    update_offset = 0

    @abstractmethod
    def __init__(self, token: str):
        self.token = token

    @abstractmethod
    async def http_get_json(self, url: str) -> dict[str, Any]:
        ...

    async def method(
        self, 
        method_name: str, 
        **kwargs: int | str | list[Any] | bool | dict[Any, Any] | list[Any]
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
            self.token,
            method_name,
            '&'.join(args_serialized)
        )
        result = await self.http_get_json(url)

        if not result["ok"]:
            raise TelegramError(
                result["error_code"],
                result["description"]
            )

        return cast(dict[str, Any] | list[Any], result["result"])

    async def send_message(self, text: str, chat_id: int) -> None:
        await self.method("sendMessage", text=text, chat_id=chat_id)

    async def delete_message(self, message_id: int, chat_id: int) -> None:
        await self.method("deleteMessage", chat_id=chat_id, message_id=message_id)

    async def poll_posts(self, chat_id: int) -> list[Message]:
        res = await self.method(
            "getUpdates",
            timeout=self.longpoll_timeout,
            allowed_updates=["channel_post"],
            offset=self.update_offset
        )
        assert type(res) is list[dict[str, Any]]

        if len(res) == 0:
            return []

        result = []
        self.update_offset = res[-1]["update_id"]

        for update in res:
            if "text" not in update["channel_post"].keys():
                continue

            result.append(Message.from_dict(update["channel_post"]))

        return result