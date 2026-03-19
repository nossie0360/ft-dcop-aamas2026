import json

class Config:
    def __init__(self):
        # Initialize configuration parameters with default values.
        self.problem_type: str = "graph_coloring"    # "graph_coloring" or "delivery_scheduling"
        self.seed: int = 82975903
        self.output_dir: str = "out"
        self.log_dir: str = "log"
        self.create_timed_subdir: bool = True
        self.log_level: str = "info"

        self.key_dir: str = "config/keys"
        self.board_num: int = 12

        self.problem_path: str = "dcop/graph-coloring/n12/graph00.csv"
        self.color_num: int = 3
        self.timeslot_num: int = 8

        self.default_value: int = 1
        self.fault_num: int = 0
        self.fault_bound: int = 1

        self.algorithm: str= "max-sum"
        self.sign_mode: str = "none"
        self.step_max: int = 1000
        self.step_min: int = 50
        self.damping_factor: float = 0.
        self.fault_utility_factor: float = 100.
        self.epsilon: float = 1e-15
        self.message_queue_size: int = 0
        self.penalty_coef: float = 1e-5

    def _strtobool(self, s: str) -> bool:
        lower_s = s.lower()
        if lower_s in ["y", "yes", "t", "true", "on", "1"]:
            return True
        elif lower_s in ["n", "no", "f", "false", "off", "0"]:
            return False
        else:
            raise ValueError(f"Invalid boolean value: {s}")

    def update(self, d: dict):
        for key, value in d.items():
            if hasattr(self, key):
                target_type = type(getattr(self, key))
                if target_type is bool and type(value) is str:
                    cast_value = self._strtobool(value)
                else:
                    cast_value = target_type(value)
                setattr(self, key, cast_value)
            else:
                raise KeyError(f"Unknown configuration parameter: {key}")

    def read_json(self, path_str: str):
        with open(path_str, "r") as f:
            config_dict = json.load(f)
        self.update(config_dict)

    def parse_args(self, args: list[str]):
        """Parses command-line arguments and updates the configuration."""
        for arg in args:
            if "=" not in arg:
                continue
            key, value = arg.split("=", 1)
            self.update({key: value})
