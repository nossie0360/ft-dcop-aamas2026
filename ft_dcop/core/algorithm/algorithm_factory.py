from asyncio import Queue
from typing import Any

from rsa import PrivateKey, PublicKey

from ..common.constants import STR_MAX_SUM, STR_REPL_MAX_SUM
from ..common.config import Config
from ..common.function import Function
from ..common.node_alloc import NodeAlloc
from .max_sum import MaxSumActor
from .repl_max_sum import ReplMaxSumActor

def create_actor(
    algorithm: str,
    host_id: int,
    node_alloc: NodeAlloc,
    neighbors: list[NodeAlloc],
    domains: dict[int, list[int]],
    private_key: str,
    public_keys: dict[int, str],
    shared_keys: dict[int, bytes],
    transfer_manager: Any,
    result_queue: Queue,
    config: Config,
    func: Function =None,
    faulty=False,
    sign_mode:str=None,
    fault_bound: int=None,
    all_nodes: list[NodeAlloc]=None,
) -> MaxSumActor|ReplMaxSumActor:

    if algorithm == STR_MAX_SUM:
        return MaxSumActor(
            host_id=host_id,
            node_alloc=node_alloc,
            neighbors=neighbors,
            domains=domains,
            private_key=private_key,
            public_keys=public_keys,
            shared_keys=shared_keys,
            transfer_manager=transfer_manager,
            result_queue=result_queue,
            config=config,
            func=func,
            faulty=faulty,
            sign_mode=sign_mode
        )
    elif algorithm == STR_REPL_MAX_SUM:
        return ReplMaxSumActor(
            host_id=host_id,
            node_alloc=node_alloc,
            neighbors=neighbors,
            domains=domains,
            fault_bound=fault_bound,
            private_key=private_key,
            public_keys=public_keys,
            shared_keys=shared_keys,
            transfer_manager=transfer_manager,
            result_queue=result_queue,
            config=config,
            func=func,
            faulty=faulty,
            sign_mode=sign_mode,
        )
    else:
        raise NotImplementedError
