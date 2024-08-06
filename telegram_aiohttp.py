import aiohttp

import abstract_telegram
from abstract_telegram import JSONAtomic

from typing import cast, Any
from dataclasses import dataclass

class BotController(abstract_telegram.BotController):
    async def http_get_json(self, url: str) -> dict[str, JSONAtomic]:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as result:
                try:
                    return cast(dict[str, JSONAtomic], await result.json())
                except Exception as e:
                    raise abstract_telegram.NetworkError from e