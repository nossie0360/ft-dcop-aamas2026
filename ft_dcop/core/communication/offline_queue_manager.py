import asyncio

class OfflineQueueManager:
    def __init__(self):
        self._queue_dict: dict[str, asyncio.Queue] = {}
        self._topic_registered_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self._message_count = 0

    def register_topic(self, topic: str, maxsize: int):
        """
        Registers a topic and creates a queue for it.
        This method is synchronous. It notifies any tasks that are waiting for this topic.
        """
        if topic not in self._queue_dict:
            self._queue_dict[topic] = asyncio.Queue(maxsize)
            event = self._topic_registered_events.get(topic, None)
            if event:
                event.set()

    async def get_queue(self, topic: str) -> asyncio.Queue:
        """
        Gets the queue for a topic. If the topic is not yet registered,
        it waits asynchronously until it is.
        """
        queue = self._queue_dict.get(topic, None)
        if queue:
            return queue

        # If the queue doesn't exist, add a queue for the topic.
        async with self._lock:
            # Check again
            queue = self._queue_dict.get(topic)
            if queue is not None:
                return queue
            if topic in self._topic_registered_events:
                event = self._topic_registered_events[topic]
            else:
                event = asyncio.Event()
                self._topic_registered_events[topic] = event

        # Wait for registration to complete
        await event.wait()

        return self._queue_dict[topic]

    def get_queue_nowait(self, topic: str) -> asyncio.Queue:
        """
        Synchronously gets the queue for a topic.
        Raises ValueError if the topic is not registered.
        """
        if topic not in self._queue_dict:
            raise ValueError(f"Topic {topic} not registered")
        return self._queue_dict[topic]

    def get_message_count(self) -> int:
        return self._message_count

    def reset_message_count(self):
        self._message_count = 0

    def add_message_count(self, count: int = 1):
        self._message_count += count
