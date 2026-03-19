import asyncio
import logging
import numpy as np
from rsa import PrivateKey, PublicKey
from typing import Any

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
    verify_pkc,
)
from ..communication.mailbox import Mailbox
from ..communication.offline_mailbox import OfflineMailbox

logger = logging.getLogger(STR_LOGGER_NAME)

class ReplMessage:
    """Class representing a message"""
    def __init__(
        self,
        src_node_id: int,
        sequence: int,
        content: np.ndarray|tuple,
        sender_host: int,
        signature: bytes = b""
    ) -> None:
        self.src_node_id: int = src_node_id
        self.sequence: int = sequence
        self.content: np.ndarray|tuple = content
        self.sender_host: int = sender_host
        self.signature: bytes = signature

    @property
    def payload(self) -> tuple:
        """Get payload for signature"""
        return (self.src_node_id, self.sequence, self.content)

    def is_same_content(self, other: 'ReplMessage') -> bool:
        """Check if the content of the message is the same"""
        if not isinstance(other, ReplMessage):
            return False

        if (self.src_node_id != other.src_node_id or
            self.sequence != other.sequence):
            return False

        if isinstance(self.content, np.ndarray) and isinstance(other.content, np.ndarray):
            return np.all(np.equal(self.content, other.content))
        elif isinstance(self.content, tuple) and isinstance(other.content, tuple):
            return self.content == other.content
        return False

    def get_payload_hash(self) -> int:
        """Get hash value of the payload"""
        if isinstance(self.content, np.ndarray):
            payload = (
                self.src_node_id, self.sequence, bytes(self.content.tobytes())
            )
            return hash(payload)
        return hash(self.payload)


class ReplMaxSumActor:
    def __init__(
            self,
            host_id: int,
            node_alloc: NodeAlloc,
            neighbors: list[NodeAlloc],
            domains: dict[int, list[int]],
            fault_bound: int,
            private_key: PrivateKey,
            public_keys: dict[int, PublicKey],
            shared_keys: dict[int, bytes],
            transfer_manager: Any,
            result_queue: asyncio.Queue,
            config: Config,
            func: Function =None,
            faulty=False,
            sign_mode=STR_NONE
    ) -> None:
        """Initialize the actor with necessary parameters.

        Args:
            host_id (int): Host ID of this actor.
            node_alloc (NodeAlloc): Node allocation information.
            neighbors (list[NodeAlloc]): List of neighbor node allocations.
            domains (dict[int, list[int]]): Domain values for each node.
            fault_bound (int): Fault tolerance bound.
            private_key (PrivateKey): Private key for signing.
            public_keys (dict[int, PublicKey]): Public keys for verification.
            shared_keys (dict[int, bytes]): Shared keys for HMAC.
            transfer_manager (Any): Transfer manager object.
            result_queue (asyncio.Queue): Queue for storing results.
            config (Config): Config object.
            func (Function, optional): Function for function node. Defaults to None.
            faulty (bool, optional): Whether this node is faulty. Defaults to False.
            sign_mode (str, optional): Signature mode. Defaults to STR_NONE.
        """

        if not (node_alloc.type == STR_VARIABLE or node_alloc.type == STR_FUNCTION):
            raise ValueError("Invalid type is passed.")
        if node_alloc.type == STR_FUNCTION and func is None:
            raise ValueError("Function is not passed to a function node.")
        self._host_id = host_id
        self._actor_id = get_actor_id(node_alloc, host_id)
        self._node_id = node_alloc.id
        self._node_type = node_alloc.type
        self._optimal_value = 0
        self._neighbors = sorted(neighbors, key=lambda x:x.id)
        sorted_domain_items = sorted(domains.items(), key=lambda x: x[0])
        self._domains = {key: value for key, value in sorted_domain_items}
        self._fault_bound = fault_bound
        self._private_key = private_key
        self._public_keys = public_keys
        self._shared_keys = shared_keys
        self._func = func
        self._faulty = faulty
        self._sign_mode = sign_mode
        self._result_queue = result_queue

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
        self._neighbor_mboxes: dict[int, dict[int, Mailbox]] = {}
        for node in self._neighbors:
            self._neighbor_mboxes[node.id] = {
                host: OfflineMailbox(
                    STR_SEND,
                    get_actor_id(node, host),
                    transfer_manager,
                    config.message_queue_size
                )
                for host in [node.primary] + node.backup_main
            }

        self._received_messages: dict[tuple[int, int], list[ReplMessage]] = {}  # (node_id, seq) -> messages
        self._message_counts: dict[tuple[int, int], dict[int, int]] = {}  # (node_id, seq) -> {payload_hash -> count}
        self._sequence = 0

        self._start_clock = 0.
        self._terminated_dict = {neighbor.id: False for neighbor in self._neighbors}
        self._termination_clock = 0.
        self._termination_step = 0


    async def put_message(self, message: ReplMessage, mailbox: Mailbox, host: int):
        """Put a message into the specified mailbox after signing it.

        Args:
            message (ReplMessage): Message to be sent.
            mailbox (Mailbox): Mailbox to send the message to.
            host (int): Host ID to send the message to.
        """
        if self._sign_mode == STR_NONE:
            sign = b""
        elif self._sign_mode == STR_PKC:
            sign = sign_pkc(message.payload, self._private_key)
        elif self._sign_mode == STR_HMAC:
            sign = sign_hmac(message.payload, self._shared_keys[host])
        payload = {
            "src_node_id": message.src_node_id,
            "sequence": message.sequence,
            "content": message.content,
            "sender_host": self._host_id,
            "signature": sign
        }
        await mailbox.put(payload)

    async def get_message(self) -> ReplMessage:
        """Get a verified message from the actor's mailbox.

        Returns:
            ReplMessage: Verified message from the mailbox.
        """
        while True:
            # Get payload
            payload = await self._mbox.get()

            # Check its compatibility
            expected_keys = set(
                ["src_node_id", "sequence", "content", "sender_host", "signature"]
            )
            if (
                not isinstance(payload, dict)
                or not expected_keys.issubset(payload.keys())
            ):
                continue

            # Create message object
            message = ReplMessage(
                src_node_id=payload["src_node_id"],
                sequence=payload["sequence"],
                content=payload["content"],
                sender_host=payload["sender_host"],
                signature=payload["signature"]
            )

            # Verify signature
            if (
                self._sign_mode == STR_PKC
                and not verify_pkc(
                    message.payload, message.signature,
                    self._public_keys[message.sender_host]
                )
            ):
                continue
            if (
                self._sign_mode == STR_HMAC
                and not verify_hmac(
                    message.payload, message.signature,
                    self._shared_keys[message.sender_host]
                )
            ):
                continue
            break
        return message

    def is_major(self, src_node: int, seq: int, message: ReplMessage):
        """Check if a message is considered major based on received counts.

        Args:
            src_node (int): Source node ID.
            seq (int): Sequence number.
            message (ReplMessage): Message to check.
        Returns:
            bool: True if the message is major, False otherwise.
        """
        payload_hash = message.get_payload_hash()
        count = self._message_counts[(src_node, seq)].get(payload_hash, 0)
        return count >= self._fault_bound + 1

    def get_correct_message(self, src_node: int, seq: int) -> ReplMessage|None:
        """Get the correct message for a given source node and sequence number.

        Args:
            src_node (int): Source node ID.
            seq (int): Sequence number.
        Returns:
            ReplMessage | None: The correct message or None if not available.
        """
        if self._terminated_dict[src_node]:
            return ReplMessage(src_node_id=src_node,
                              sequence=seq,
                              content=(STR_TERMINATE,),
                              sender_host=-1,
                              signature=b"")

        if (src_node, seq) not in self._received_messages:
            return None
        for message in self._received_messages[(src_node, seq)]:
            if self.is_major(src_node, seq, message):
                return message
        return None

    def get_ready_messages(self, seq: int) -> dict[int, ReplMessage]|None:
        """Get ready messages for all neighbors with a given sequence number.

        Args:
            seq (int): Sequence number.
        Returns:
            dict[int, ReplMessage] | None: Dictionary of ready messages or None.
        """
        correct_messages = {node.id: self.get_correct_message(node.id, seq)
                            for node in self._neighbors}
        if None in correct_messages.values():
            return None
        else:
            return correct_messages

    def received_hosts(self, src_node: int, seq: int) -> list[int]:
        """Get the list of hosts from which messages have been received for a given source node and sequence.

        Args:
            src_node (int): Source node ID.
            seq (int): Sequence number.
        Returns:
            list[int]: List of sender host IDs.
        """
        if (src_node, seq) not in self._received_messages:
            return []
        messages = self._received_messages[(src_node, seq)]
        return [msg.sender_host for msg in messages]

    async def multicast(self, messages: dict[int, ReplMessage], mboxes: dict[int, Mailbox]):
        """Multicast messages to specified hosts' mailboxes.

        Args:
            messages (dict[int, ReplMessage]): Messages to send.
            mboxes (dict[int, Mailbox]): Mailboxes to send to.
        """
        for host, message in messages.items():
            await self.put_message(message, mboxes[host], host)

    async def send(self, content_list: list|np.ndarray):
        """Send content to all neighbors.

        Args:
            content_list (list | np.ndarray): List or array of message contents for each neighbor.
        """
        for i, neighbor in enumerate(self._neighbors):
            message = ReplMessage(
                src_node_id=self._node_id,
                sequence=self._sequence,
                content=content_list[i],
                sender_host=self._host_id
            )
            message_dict = {
                host: message
                for host in self._neighbor_mboxes[neighbor.id].keys()
            }
            await self.multicast(message_dict, self._neighbor_mboxes[neighbor.id])

    def add_message(self, message: ReplMessage):
        """Add message and update message counts.

        Args:
            message (ReplMessage): Message to add.
        """
        src_node = message.src_node_id
        seq = message.sequence

        if (src_node, seq) not in self._received_messages:
            self._received_messages[(src_node, seq)] = []
            self._message_counts[(src_node, seq)] = {}

        self._received_messages[(src_node, seq)].append(message)

        payload_hash = message.get_payload_hash()
        self._message_counts[(src_node, seq)][payload_hash] = (
            self._message_counts[(src_node, seq)].get(payload_hash, 0) + 1
        )

    def garbage_collection(self, threshold_step: int=10):
        """Perform garbage collection on old messages.

        Args:
            threshold_step (int, optional): Step threshold for garbage collection. Defaults to 10.
        """
        old_keys = [k for k in self._received_messages
                    if k[1] <= self._sequence - threshold_step]
        for key in old_keys:
            self._received_messages.pop(key)
            self._message_counts.pop(key)

    async def close(self):
        """Close the actor's mailbox and neighbor mailboxes.
        """
        await self._mbox.close()

    async def receive(
        self, terminated_dict: dict[int, bool]
    )-> tuple[dict[int, ReplMessage], dict[int, bool]]:
        """Receive messages until all ready messages for the current sequence are collected.

        Args:
            terminated_dict (dict[int, bool]): Dictionary indicating which neighbors are terminated.
        Returns:
            tuple[dict[int, ReplMessage], dict[int, bool]]: Ready messages and updated termination dictionary.
        """
        while True:
            if all(terminated_dict.values()):
                ready_messages = {neighbor.id: ReplMessage(src_node_id=neighbor.id,
                                                           sequence=self._sequence,
                                                           content=(STR_TERMINATE,),
                                                           sender_host=-1,
                                                           signature=b"")
                                  for neighbor in self._neighbors}
                break
            message = await self.get_message()
            src_node = message.src_node_id
            seq = message.sequence
            host = message.sender_host
            if host in self.received_hosts(src_node, seq):
                continue
            self.add_message(message)

            ready_messages = self.get_ready_messages(self._sequence)
            if ready_messages is not None:
                break

        self._sequence += 1
        self.garbage_collection()
        return ready_messages, terminated_dict

    async def termination_process(self):
        """Execute the termination process for the actor.
        """
        # Send a terminate message
        terminate_messages = [(STR_TERMINATE,) for neighbor in self._neighbors]
        await self.send(terminate_messages)

        # Record the termination time
        self._termination_clock = time.monotonic_ns()

        # Store the result
        result = (
            self._actor_id,
            self._optimal_value,
            self._termination_step,
            (self._termination_clock - self._start_clock) * 1e-9
        )
        await self._result_queue.put(result)

        # Close
        await self.close()

        logger.info(f"[0x{self._actor_id:08x}] Terminated")


    async def run(self):
        """Run the main logic of the actor.
        """
        logger.info(f"[0x{self._actor_id:08x}] Start running repl-max-sum.")
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
        """Run the Repl-Max-Sum algorithm for a variable node.
        """
        step = 0
        converge_step = 0
        domain = self._domains[self._node_id]
        domain_len = len(domain)
        q_function = np.zeros((len(self._neighbors), domain_len))
        pre_q_function = None
        pre_z_function = None
        r_function = np.zeros((len(self._neighbors), domain_len))

        while (
            not termination_condition(
                step, converge_step, self._step_max, self._step_min
            )
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
                message_contents = [(None,) for neighbor in self._neighbors]
            else:
                message_contents = q_function
            await self.send(message_contents)
            messages, self._terminated_dict = await self.receive(self._terminated_dict)
            for i, neighbor in enumerate(self._neighbors):
                message = messages[neighbor.id]
                content = message.content
                if self._terminated_dict[neighbor.id]:
                    continue
                elif isinstance(content, tuple) and content[0] == STR_TERMINATE:
                    self._terminated_dict[neighbor.id] = True
                elif isinstance(content, np.ndarray):
                    r_function[i] = content
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
        """Run the Repl-Max-Sum algorithm for a function node.
        """
        step = 0
        converge_step = 0
        q_function = [np.zeros(len(self._domains[neighbor.id])) for neighbor in self._neighbors]
        r_function = [np.zeros(len(self._domains[neighbor.id])) for neighbor in self._neighbors]
        pre_r_function = None
        variables = [neighbor.id for neighbor in self._neighbors]
        optimizer = LocalOptimizer(variables, self._domains)
        optimizer.update_function_table(variables, self._domains, self._func)

        while (
            not termination_condition(
                step, converge_step, self._step_max, self._step_min
            )
            and not all(self._terminated_dict.values())
        ):
            # Calculate r function
            for i, neighbor in enumerate(self._neighbors):
                next_r = optimizer.optimize_for_variable(q_function, neighbor.id)
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
                message_contents = [(None,) for neighbor in self._neighbors]
            else:
                message_contents = r_function
            await self.send(message_contents)
            messages, self._terminated_dict = await self.receive(self._terminated_dict)
            for i, neighbor in enumerate(self._neighbors):
                message = messages[neighbor.id]
                content = message.content
                if self._terminated_dict[neighbor.id]:
                    continue
                elif isinstance(content, tuple) and content[0] == STR_TERMINATE:
                    self._terminated_dict[neighbor.id] = True
                elif isinstance(content, np.ndarray):
                    q_function[i] = content

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
