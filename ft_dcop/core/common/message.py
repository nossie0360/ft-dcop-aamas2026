from typing import Any

class Message:
    def __init__(self, src: int, dest: int, payload: Any):
        self.src = src
        self.dest = dest
        self.payload = payload
