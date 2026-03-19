class NodeAlloc:
    def __init__(
        self,
        type: str,
        id: int,
        primary: int,
        backup_main: list[int],
        backup_sub: list[int],
        variables: list[int]
    ):
        self.type = type
        self.id = id
        self.primary = primary
        self.backup_main = backup_main
        self.backup_sub = backup_sub
        self.variables = variables
