import asyncio
import datetime
import json
import logging
from pathlib import Path
import random
import time

from ..core.dcop.graph_coloring import GraphColoringManager
from ..core.common.replica_allocation import allocate_primary_backup_fixed_group
from ..core.common.crypto_key import (
    read_private_key,
    read_public_key,
    read_shared_key
)
from ..core.algorithm.algorithm_factory import create_actor
from ..core.communication.offline_queue_manager import OfflineQueueManager
from ..core.common.config import Config
from ..core.common.constants import (
    CONFIG_PATH,
    NODE_LIMIT,
    STR_MAX_SUM,
    STR_REPL_MAX_SUM,
    STR_VARIABLE,
    STR_FUNCTION,
    STR_LOGGER_NAME,
    STR_GRAPH_COLORING,
    STR_DELIVERY_SCHEDULING
)
from ..core.common.logger import configure_logger, log_level
from ..core.common.utility import (
    get_replicas,
    global_function_value,
    actor_id,
    host_id
)
from ..core.dcop.graph_coloring import GraphColoringManager
from ..core.dcop.delivery_scheduling import DeliverySchedulingManager


logger = logging.getLogger(STR_LOGGER_NAME)

async def run_simulation(config: Config):
    """
    Main function to run the DCOP simulation.
    """
    start_time = time.perf_counter()
    random.seed(config.seed)

    # --- Step 1: Prepare the output dir ---
    output_dir = Path(config.output_dir)
    output_dir.mkdir(exist_ok=True)

    if config.algorithm not in [STR_MAX_SUM, STR_REPL_MAX_SUM]:
        logger.warning(
            f"In the current implementation, replica allocation is only for max-sum and repl-max-sum "
            f"(i.e., no sub-backup replicas are allocated)."
        )

    # --- Step 2: Load Problem & Convert to DCOP ---
    if config.problem_type == STR_GRAPH_COLORING:
        logger.info(f"Loading graph from: {config.problem_path}")
        problem_path = Path(config.problem_path)
        functions = GraphColoringManager.generate_functions_from_adjlist_file(
            problem_path,
            penalty_coef=config.penalty_coef,
            default_value=config.default_value
        )
    elif config.problem_type == STR_DELIVERY_SCHEDULING:
        problem_path = Path(config.problem_path)
        logger.info(f"Loading delivery scheduling instance from: {config.problem_path}")
        delivery_tasks = DeliverySchedulingManager.load_problem_instance(problem_path)
        functions = DeliverySchedulingManager.create_functions(delivery_tasks)

    variables: set[int] = set()
    for func in functions:
        variables.update(func.variables)

    if config.problem_type == STR_GRAPH_COLORING:
        num_agents = len(variables)
        agent_variables_map = None
    elif config.problem_type == STR_DELIVERY_SCHEDULING:
        agent_variables_map = {}
        for task in delivery_tasks:
            if task.agent_id not in agent_variables_map:
                agent_variables_map[task.agent_id] = []
            agent_variables_map[task.agent_id].append(task.task_id)
        num_agents = len(agent_variables_map)

    logger.info(f"Problem loaded: {len(variables)} variables, {len(functions)} functions.")

    # --- Step 3: Allocate Roles ---
    logger.info("Allocating roles to agents...")
    backup_main_num = 2 * config.fault_bound
    backup_sub_num = 0      # No sub backups in this implementation
    alloc_variables, alloc_functions = allocate_primary_backup_fixed_group(
        functions, num_agents, backup_main_num, backup_sub_num, agent_variables_map
    )
    all_nodes = alloc_variables | alloc_functions
    logger.info("Role allocation complete.")

    # --- Step 4: Prepare Communication & Auth ---
    logger.info("Loading cryptographic keys...")
    key_dir = Path(config.key_dir)
    try:
        private_key = read_private_key(key_dir)
        public_key = read_public_key(key_dir)
        shared_key = read_shared_key(key_dir)

        # Create key dictionaries for all agents
        public_keys = {i: public_key for i in range(num_agents)}
        shared_keys = {i: shared_key for i in range(num_agents)}
        logger.info("Keys loaded successfully.")
    except FileNotFoundError as e:
        logger.error(f"Key files not found in {key_dir}. Please generate them first. Error: {e}")
        return

    # --- Step 5: Setup Agent Environment ---
    # For asyncio simulation, we use an offline manager that simulates communication
    # with async queues within a single process.
    transfer_manager = OfflineQueueManager()

    # --- Step 6: Configure and Create Actors ---
    logger.info(f"Creating actors for algorithm: {config.algorithm}...")
    result_queue = asyncio.Queue(config.message_queue_size)
    actors = []

    # Determine faulty agents
    faulty_agent_ids = [i * 3 for i in range(config.fault_num)] # e.g., agents 0, 3, 6, ... are faulty

    for node_alloc in all_nodes.values():
        replicas = get_replicas(node_alloc, config.algorithm)
        for host in replicas:
            # Determine neighbors
            neighbor_nodes = []
            if node_alloc.type == STR_VARIABLE:
                # Neighbors of a variable are its connected functions
                for func_alloc in alloc_functions.values():
                    if node_alloc.id in func_alloc.variables:
                        neighbor_nodes.append(func_alloc)
            else: # STR_FUNCTION
                # Neighbors of a function are its connected variables
                for var_id in node_alloc.variables:
                    neighbor_nodes.append(alloc_variables[var_id])

            # Determine domains
            if config.problem_type == STR_GRAPH_COLORING:
                domains = {
                    var_id: list(range(1, config.color_num + 1))
                    for var_id in variables
                }
            elif config.problem_type == STR_DELIVERY_SCHEDULING:
                domains = {
                    task.task_id: list(range(config.timeslot_num))
                    for task in delivery_tasks
                }

            # Determine if faulty
            is_faulty = host in faulty_agent_ids

            # Get function if it's a function node
            func_obj = next(
                (f for f in functions if f.id == (node_alloc.id - NODE_LIMIT)),
                None
            ) if node_alloc.type == STR_FUNCTION else None

            actor = create_actor(
                algorithm=config.algorithm,
                host_id=host,
                node_alloc=node_alloc,
                neighbors=neighbor_nodes,
                domains=domains,
                private_key=private_key,
                public_keys=public_keys,
                shared_keys=shared_keys,
                transfer_manager=transfer_manager,
                result_queue=result_queue,
                config=config,
                func=func_obj,
                faulty=is_faulty,
                sign_mode=config.sign_mode,
                fault_bound=config.fault_bound,
                all_nodes=all_nodes
            )
            actors.append(actor)

    logger.info(f"Created {len(actors)} actors.")

    # --- Step 7: Run the Algorithm ---
    logger.info("Starting simulation...")
    transfer_manager.reset_message_count()
    tasks = [asyncio.create_task(actor.run()) for actor in actors]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All actor tasks have completed.")

    # --- Step 8: Aggregate and Save Results ---
    logger.info("Aggregating results...")
    results = []
    while not result_queue.empty():
        results.append(await result_queue.get())

    ## result: (actor_id, optimal_value, termination_step, runtime)

    # Post-processing and analysis
    final_values = {res[0]: res[1] for res in results if res} # actor_id -> value
    primary_actor_ids = {
        node.id: actor_id(node.primary, node.id, 0)
        for node in alloc_variables.values()
    }
    primary_values = {
        k: final_values.get(v, config.default_value)
        for k, v in primary_actor_ids.items()
    }
    # Replace with the default value for faulty agents
    # for fault in faulty_agent_ids:
    #     primary_values[fault] = config.default_value
    total_utility = global_function_value(primary_values, functions)

    # Get conflicts
    if config.problem_type == STR_GRAPH_COLORING:
        conflicts = GraphColoringManager.get_conflict_counts(
            functions=functions,
            x=primary_values,
            default_value=config.default_value,
            ignore_default_value=False
        )
    elif config.problem_type == STR_DELIVERY_SCHEDULING:
        conflict_dict = DeliverySchedulingManager.get_constraint_violations(
            tasks=delivery_tasks,
            assignment=primary_values
        )
        conflicts = sum(conflict_dict.values())

    steps = [
        res[2] for res in results
        if host_id(res[0]) not in faulty_agent_ids
    ]
    max_step = max(steps)
    runtimes = [
        res[3] for res in results
        if host_id(res[0]) not in faulty_agent_ids
    ]
    max_runtime = max(runtimes)

    simulation_duration = time.perf_counter() - start_time

    output_data = {
        "simulation_parameters": vars(config),
        "results": {
            "simulation_duration_sec": simulation_duration,
            "total_message_count": transfer_manager.get_message_count(),
            "agents_num": num_agents,
            "actors_num": len(actors),
            "max_step": max_step,
            "max_runtime_sec": max_runtime,
            "total_utility": total_utility,
            "conflict_count": conflicts,
            "final_agent_values": {f"agent_{k:02d}": v for k, v in primary_values.items()},
            "raw_results": results
        }
    }

    # Save results to file
    node_num_dir = output_dir / f"n{num_agents}"
    if not node_num_dir.exists():
        node_num_dir.mkdir()
    output_filename = f"{problem_path.stem}_{config.algorithm}_b{config.fault_num}_k{config.fault_bound}.json"
    output_path = node_num_dir / output_filename
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=4)

    logger.info(f"Simulation finished in {simulation_duration:.2f} seconds.")
    logger.info(f"Results saved to {output_path}")


def main(args: list[str]):
    config = Config()
    config.read_json(CONFIG_PATH)
    config.parse_args(args)

    if config.create_timed_subdir:
        now_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        config.log_dir += f"/{now_str}"
        config.output_dir += f"/{now_str}"

    log_path = Path(config.log_dir) / "log.txt"
    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True)

    configure_logger(
        STR_LOGGER_NAME,
        log_path,
        level=log_level(config.log_level)
    )

    try:
        asyncio.run(run_simulation(config))
    except KeyboardInterrupt:
        logger.info("Simulation cancelled by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
