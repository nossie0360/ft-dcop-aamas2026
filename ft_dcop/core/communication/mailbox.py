from typing import Any

from ..common.constants import STR_SEND, STR_RECEIVE

class Mailbox:
    """
    Interface for a Mailbox.
    Defines the methods that a Mailbox implementation should provide.
    """
    def __init__(
        self,
        mode: str,
        dest_actor_id: int,
        transfer_manager: Any,
    ):
        if mode not in [STR_SEND, STR_RECEIVE]:
            raise ValueError("Invalid mode")
        self._mode = mode
        self._dest_actor_id = dest_actor_id
        self._transfer_manager = transfer_manager

    async def put(self, message: Any):
        raise NotImplementedError

    async def get(self) -> Any:
        raise NotImplementedError

    def is_empty(self) -> bool:
        raise NotImplementedError

    async def close(self):
        raise NotImplementedError
