import logging
import numpy as np
from rsa import PrivateKey, PublicKey
from typing import Any

import asyncio
import random
import time
import traceback

from ..common.constants import (
    STR_VARIABLE,
    STR_FUNCTION,
    STR_TERMINATE,
    STR_NONE,
    STR_PKC,
    STR_HMAC,
    STR_SEND,
    STR_RECEIVE,
    STR_LOGGER_NAME,
)
from ..common.config import Config
from ..common.function import Function
from ..common.local_optimizer import LocalOptimizer
from ..common.node_alloc import NodeAlloc
from ..common.utility import (
    get_actor_id,
    concat_array,
    termination_condition,
    convergence_detection,
    sign_hmac,
    sign_pkc,
    verify_hmac,
    verify_pkc
)
from ..communication.mailbox import Mailbox
from ..communication.offline_mailbox import OfflineMailbox

logger = logging.getLogger(STR_LOGGER_NAME)


class MaxSumActor:
    """Implementation of the Max-Sum algorithm actor."""
    def __init__(
            self,
            host_id: int,
            node_alloc: NodeAlloc,
            neighbors: list[NodeAlloc],
            domains: dict[int, list[int]],
            private_key: PrivateKey,
            public_keys: dict[int, PublicKey],
            shared_keys: dict[int, bytes],
            transfer_manager: Any,
            result_queue: asyncio.Queue,
            config: Config,
            func: Function =None,
            faulty=False,
            sign_mode:str=STR_NONE
    ) -> None:
        """Initialize a Max-Sum actor.

        Args:
            host_id (int): ID of the host
            node_alloc (NodeAlloc): Node allocation information
            neighbors (list[NodeAlloc]): List of neighbor node allocations
            domains (dict[int, list[int]]): Dictionary mapping node IDs to their domains
            private_key (PrivateKey): Private key for signing messages
            public_keys (dict[int, PublicKey]): Dictionary mapping host IDs to public keys
            shared_keys (dict[int, bytes]): Dictionary mapping host IDs to shared keys
            transfer_manager (Any): Transfer manager object
            result_queue (asyncio.Queue): Queue for storing actor results
            func (Function, optional): Function object (required for function nodes). Defaults to None.
            faulty (bool, optional): Whether the node should behave faulty. Defaults to False.
            sign_mode (str, optional): Signature mode (HMAC, PKC, or NONE). Defaults to STR_NONE.
        """

        if not (node_alloc.type == STR_VARIABLE or node_alloc.type == STR_FUNCTION):
            raise ValueError("Invalid type is passed.")
        if node_alloc.type == STR_FUNCTION and func is None:
            raise ValueError("Function is not passed to a function node.")

        self._host_id = host_id
        self._actor_id = get_actor_id(node_alloc, host_id)
        self._node_id = node_alloc.id
        self._node_type = node_alloc.type
        self._private_key = private_key
        self._public_keys = public_keys
        self._shared_keys = shared_keys
        self._sign_mode = sign_mode
        self._optimal_value = 0
        neighbors_id = [neighbor.id for neighbor in neighbors]
        self._neighbors = sorted(neighbors_id)
        self._neighbor_hosts = {node.id: node.primary for node in neighbors}
        sorted_domain_items = sorted(domains.items(), key=lambda x: x[0])
        self._domains = {key: value for key, value in sorted_domain_items}
        self._func = func
        self._faulty = faulty

        # Read from config
        self._step_max = config.step_max
        self._step_min = config.step_min
        self._damping_factor = config.damping_factor
        self._epsilon = config.epsilon
        self._fault_utility_factor = config.fault_utility_factor

        self._mbox = OfflineMailbox(
            STR_RECEIVE, self._actor_id, transfer_manager,
            config.message_queue_size
        )
        self._neighbor_mboxes = {
            node.id: OfflineMailbox(
                STR_SEND,
                get_actor_id(node, node.primary),
                transfer_manager,
                config.message_queue_size
            )
            for node in neighbors
        }

        self._start_clock = 0.
        self._result_queue = result_queue
        self._terminated_dict = {neighbor: False for neighbor in self._neighbors}
        self._termination_clock = 0.
        self._termination_step = 0


    async def close(self):
        """Close the actor's mailbox and neighbor mailboxes.
        """
        await self._mbox.close()

    async def put_message(self, payload: Any, mailbox: Mailbox, host: int):
        """Put a signed message into a mailbox.

        Args:
            payload (Any): Message payload
            mailbox (Mailbox): Destination mailbox
            host (int): Destination host ID
        """
        if self._sign_mode == STR_NONE:
            sign = b""
        elif self._sign_mode == STR_PKC:
            sign = sign_pkc(payload, self._private_key)
        elif self._sign_mode == STR_HMAC:
            sign = sign_hmac(payload, self._shared_keys[host])
        message = (payload, self._host_id, sign)
        await mailbox.put(message)

    async def get_message(self) -> Any:
        """Get a verified message from the actor's mailbox.

        Returns:
            Any: Verified message from the mailbox.
        """
        while True:
            message, host, sign = await self._mbox.get()
            if (
                self._sign_mode == STR_PKC
                and not verify_pkc(message, sign, self._public_keys[host])
            ):
                continue
            if (
                self._sign_mode == STR_HMAC
                and not verify_hmac(message, sign, self._shared_keys[host])
            ):
                continue
            break
        return message

    async def send(self, content_list: list|np.ndarray):
        """Send content to all neighbors.

        Args:
            content_list (list | np.ndarray): List or array of message contents for each neighbor.
        """
        for i, neighbor in enumerate(self._neighbors):
            payload = (self._node_id, content_list[i])
            host = self._neighbor_hosts[neighbor]
            await self.put_message(payload, self._neighbor_mboxes[neighbor], host)

    async def receive(
        self, buffers: dict[int, list], terminated_dict: dict[int, bool]
    )-> tuple[dict[int, list], dict[int, bool]]:
        """Receive messages until all ready messages are collected.

        Args:
            buffers (dict[int, list]): Dictionary mapping neighbor IDs to message buffers
            terminated_dict (dict[int, bool]): Dictionary indicating which neighbors are terminated

        Returns:
            tuple[dict[int, list], dict[int, bool]]: Updated buffers and termination dictionary
        """
        while True:
            if all([len(buf) > 0 for buf in buffers.values()]):
                break
            if all(terminated_dict.values()):
                break
            message = await self.get_message()
            sender = message[0]
            if type(message[1]) == str and message[1] == STR_TERMINATE:
                terminated_dict[sender] = True
            buffers[sender].append(message)
        return buffers, terminated_dict

    async def termination_process(self):
        """Execute the termination process for the actor.

        Sends termination messages to neighbors, records termination time,
        flushes pending messages, and stores the result.
        """
        # Send a terminate message
        terminate_messages = [STR_TERMINATE for neighbor in self._neighbors]
        await self.send(terminate_messages)

        # Record the termination time
        self._termination_clock = time.monotonic_ns()

        # Store the result
        result = (
            self._actor_id,
            self._optimal_value,
            self._termination_step,
            (self._termination_clock - self._start_clock) * 1e-9,
        )
        await self._result_queue.put(result)

        # Close the mailbox
        await self._mbox.close()

        logger.info(f"[0x{self._actor_id:08x}] Terminated")


    async def run(self):
        """Run the main logic of the actor.
        """
        logger.info(f"[0x{self._actor_id:08x}] Start running max-sum.")
        self._start_clock = time.monotonic_ns()
        try:
            # Run the algorithm
            if self._node_type == STR_VARIABLE:
                await self.variable_run()
            elif self._node_type == STR_FUNCTION:
                await self.function_run()

        except asyncio.TimeoutError:
            logger.warning(f"[0x{self._actor_id:08x}] TimeoutError occurred.")
            await self.termination_process()

        except BaseException as e:
            logger.error(f"[0x{self._actor_id:08x}] {traceback.format_exception(e)}")
            raise e

    async def variable_run(self):
        """Run the Max-Sum algorithm for a variable node.
        """
        step = 0
        converge_step = 0
        buffers = {neighbor: [] for neighbor in self._neighbors}
        domain = self._domains[self._node_id]
        domain_len = len(domain)
        q_function = np.zeros((len(self._neighbors), domain_len))
        pre_q_function = None
        pre_z_function = None
        r_function = np.zeros((len(self._neighbors), domain_len))

        while (
            not termination_condition(step, converge_step, self._step_max, self._step_min)
            and not all(self._terminated_dict.values())
        ):
            # Calculate q function
            sum_wo_target = np.sum(r_function, axis=0) - r_function
            alpha = - np.sum(sum_wo_target, axis=1) / domain_len
            next_q = alpha.reshape((-1, 1)) + sum_wo_target
            q_function = (
                self._damping_factor * q_function
                + (1 - self._damping_factor) * next_q
            )
            if self._faulty:
                for i, neighbor in enumerate(self._neighbors):
                    q_function[i] = np.array(
                        [random.random() for _ in range(q_function[i].size)]
                    ).reshape(q_function[i].shape)
                    q_function[i] /= np.sum(q_function[i])

            # Transfer messages
            if convergence_detection(q_function, pre_q_function, self._epsilon):
                message_contents = [None for neighbor in self._neighbors]
            else:
                message_contents = q_function
            await self.send(message_contents)
            buffers, self._terminated_dict = await self.receive(
                buffers, self._terminated_dict
            )
            for i, neighbor in enumerate(self._neighbors):
                message = buffers[neighbor][0]
                if self._terminated_dict[neighbor] and type(message[1]) == str:
                    continue
                buffers[neighbor].pop(0)
                if message[1] is not None:
                    r_function[i] = message[1]
            z_function = np.sum(r_function, axis=0)

            # Prepare for next step
            if convergence_detection(z_function, pre_z_function, self._epsilon):
                converge_step += 1
            else:
                converge_step = 0
            pre_q_function = q_function.copy()
            pre_z_function = z_function.copy()
            step += 1
            if self._node_id == 1:
                logger.info(f"[0x{self._actor_id:08x}] Proceed to next step: {step}")

        # Calculate an optimal value
        z_function = np.sum(r_function, axis=0)
        self._optimal_value = domain[np.argmax(z_function)]
        logger.info(f"[0x{self._actor_id:08x}] Z function: {z_function}")
        logger.info(f"[0x{self._actor_id:08x}] Optimal value: {self._optimal_value}")

        self._termination_step = step
        await self.termination_process()

    async def function_run(self):
        """Run the Max-Sum algorithm for a function node.
        """
        step = 0
        converge_step = 0
        buffers = {neighbor: [] for neighbor in self._neighbors}
        q_function = [np.zeros(len(self._domains[neighbor])) for neighbor in self._neighbors]
        r_function = [np.zeros(len(self._domains[neighbor])) for neighbor in self._neighbors]
        pre_r_function = None
        optimizer = LocalOptimizer(self._neighbors, self._domains)
        optimizer.update_function_table(self._neighbors, self._domains, self._func)

        while (
            not termination_condition(step, converge_step, self._step_max, self._step_min)
            and not all(self._terminated_dict.values())
        ):
            # Calculate r function
            for i, neighbor in enumerate(self._neighbors):
                next_r = optimizer.optimize_for_variable(q_function, neighbor)
                r_function[i] = (
                    self._damping_factor * r_function[i]
                    + (1 - self._damping_factor) * next_r
                )
            if self._faulty:
                for i, neighbor in enumerate(self._neighbors):
                    r_function[i] = np.array(
                        [random.random() for _ in range(r_function[i].size)]
                    ).reshape(r_function[i].shape) * self._fault_utility_factor

            # Transfer messages
            if convergence_detection(
                concat_array(r_function), concat_array(pre_r_function), self._epsilon
            ):
                message_contents = [None for neighbor in self._neighbors]
            else:
                message_contents = r_function
            await self.send(message_contents)
            buffers, self._terminated_dict = await self.receive(
                buffers, self._terminated_dict
            )
            for i, neighbor in enumerate(self._neighbors):
                message = buffers[neighbor][0]
                if self._terminated_dict[neighbor] and type(message[1]) == str:
                    continue
                buffers[neighbor].pop(0)
                if message[1] is not None:
                    q_function[i] = message[1]

            # Prepare for next step
            if convergence_detection(
                concat_array(r_function), concat_array(pre_r_function), self._epsilon
            ):
                converge_step += 1
            else:
                converge_step = 0
            pre_r_function = r_function.copy()
            step += 1
            if self._node_id == 0x1001:
                logger.info(f"[0x{self._actor_id:08x}] Proceed to next step: {step}")

        self._termination_step = step
        await self.termination_process()
