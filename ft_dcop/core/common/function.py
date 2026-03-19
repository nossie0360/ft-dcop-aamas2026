from typing import Any

class Function:
    def __init__(
        self,
        id: int,
        variables: list[int],
        function: Any
    ):
        self.id = id
        self.variables = variables
        self.function = function
