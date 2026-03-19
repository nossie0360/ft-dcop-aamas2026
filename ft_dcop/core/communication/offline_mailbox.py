import asyncio
from typing import Any

from .mailbox import Mailbox
from .offline_queue_manager import OfflineQueueManager
from ..common.constants import STR_SEND, STR_RECEIVE


class OfflineMailbox(Mailbox):
    def __init__(
        self,
        mode: str,
        dest_actor_id: int,
        transfer_manager: OfflineQueueManager,
        queue_size: int = 0
    ):
        """Initialize Offline Mailbox

        Args:
            mode ("send" or "receive"): Mode of the mailbox.
            dest_actor_id: Destination actor ID.
            transfer_manager: An instance of OfflineQueueManager.
            queue_size: Size of the message queue.

        Note:
            If the mailbox is in the receive mode, it can both receive and send messages.
            If in the send mode, it can only send messages.
        """
        # Initialize variables
        super().__init__(mode, dest_actor_id, transfer_manager)
        self._my_topic = f"message/actor_0x{dest_actor_id:08x}"
        self._offline_queue_manager = transfer_manager

        # Register the topic if the receive mode
        if self._mode == STR_RECEIVE:
            self._offline_queue_manager.register_topic(
                self._my_topic, queue_size
            )

    async def put(self, message: Any):
        self._offline_queue_manager.add_message_count()
        queue = await self._offline_queue_manager.get_queue(self._my_topic)
        await queue.put(message)

    async def get(self) -> Any:
        if self._mode != STR_RECEIVE:
            raise ValueError("Mailbox is not in receive mode")
        queue = await self._offline_queue_manager.get_queue(self._my_topic)
        return await asyncio.wait_for(queue.get(), timeout=60)  # 60 seconds timeout

    def is_empty(self) -> bool:
        if self._mode != STR_RECEIVE:
            raise ValueError("is_empty() is only for receiver mailboxes")
        # get_queue_nowait() is safe because of the receive mode.
        queue = self._offline_queue_manager.get_queue_nowait(self._my_topic)
        return queue.empty()

    async def close(self):
        if self._mode != STR_RECEIVE:
            raise ValueError("close() is only for receiver mailboxes")
        queue = await self._offline_queue_manager.get_queue(self._my_topic)
        while not queue.empty():
            queue.get_nowait()
