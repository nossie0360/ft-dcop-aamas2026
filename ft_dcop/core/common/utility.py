import hashlib
import hmac
import pickle
from typing import Any

import numpy as np
import rsa
from rsa import PrivateKey, PublicKey
from rsa import VerificationError

from .constants import (
    REPLICA_NUM_LIMIT,
    STR_MAX_SUM,
    STR_REPL_MAX_SUM,
)
from .function import Function
from .node_alloc import NodeAlloc


########################
# Utility Function Helper
########################

def global_function_value(values: dict[int, int], functions: list[Function]) -> float:
    sum_util = 0
    for func in functions:
        partial_values = {k: v for k, v in values.items() if k in func.variables}
        sum_util += func.function(partial_values)
    return sum_util

########################
# Deployment Helper
########################

def get_replicas(node_alloc: NodeAlloc, algorithm: str):
    if algorithm == STR_MAX_SUM:
        return [node_alloc.primary]
    elif algorithm == STR_REPL_MAX_SUM:
        return [node_alloc.primary] + node_alloc.backup_main


########################
# ID Helper
########################

def actor_id(host_id: int, node_id: int, role_id: int) -> int:
    """
    Return an actor ID.

    Detail:
        An actor ID is an 8-digit hex number.

        Given an actor id "aabbccdd",
        "aa" indicates a host ID,
        "bbcc" indicates a node ID,
        and "dd" indicates a role ID (e.g., a primary's ID is 0).
    """
    return (host_id << 4*6) + (node_id << 4*2) + role_id

def host_id(actor_id: int) -> int:
    return actor_id >> 4*6

def node_id(actor_id: int) -> int:
    return (actor_id & 0x00ffff00) >> 4*2

def role_id(actor_id: int) -> int:
    return actor_id & 0x000000ff

def get_role_id(node_alloc: NodeAlloc, host: int) -> int:
    host_list = [node_alloc.primary] + node_alloc.backup_main + node_alloc.backup_sub
    return host_list.index(host)

def get_actor_id(node_alloc: NodeAlloc, host: int) -> int:
    node_id = node_alloc.id
    role_id = get_role_id(node_alloc, host)
    return actor_id(host, node_id, role_id)

########################
# Data Helper
########################

def concat_array(array: list[np.ndarray]|None):
    if array is None:
        return None
    return np.concatenate(tuple(array))

def get_sha256_digest(byte_data: bytes) -> bytes:
    return hashlib.sha256(byte_data).digest()

def encode(obj: Any) -> bytes:
    return pickle.dumps(obj)

def decode(byte_data: bytes) -> Any:
    return pickle.loads(byte_data)


########################
# Max-Sum Helper
########################

def convergence_detection(
    array: np.ndarray,
    pre_array: np.ndarray|None,
    epsilon: float = 1e-15
) -> bool:
    if pre_array is None:
        return False
    error_array = abs(array - pre_array)
    threshold = epsilon * (1 + abs(array) + abs(pre_array))
    return np.all(error_array < threshold)

def termination_condition(
    step: int,
    converge_step: int,
    step_max: int = 1000,
    step_min: int = 50
) -> bool:
    return converge_step >= step_min or step >= step_max


########################
# Cryptography Helper
########################

def sign_pkc(data: Any, private_key: PrivateKey) -> bytearray:
    byte_data = encode(data)
    sign = rsa.sign(byte_data, private_key, "SHA-256")
    return sign

def verify_pkc(data: Any, sign: bytearray, public_key: PublicKey) -> bool:
    byte_data = encode(data)
    if sign is None:
        return False
    try:
        rsa.verify(byte_data, sign, public_key)
    except VerificationError:
        return False
    return True

def sign_hmac(data: Any, shared_key: bytes) -> bytearray:
    byte_data = encode(data)
    sign = bytearray(
        hmac.new(shared_key, msg=byte_data, digestmod=hashlib.sha256).digest()
    )
    return sign

def verify_hmac(data: Any, sign: bytearray, shared_key: bytes) -> bool:
    expected_sign = sign_hmac(data, shared_key)
    return sign == expected_sign
