import json
import pathlib
import random

from ..common.function import Function

class DeliveryTask:
    """Class representing a delivery task."""
    def __init__(self, task_id: int, agent_id: int, warehouse_id: int, preferred_timeslots: list[int]):
        self.task_id = task_id
        self.agent_id = agent_id
        self.warehouse_id = warehouse_id
        self.preferred_timeslots = preferred_timeslots

class PreferredTimeslotUtility:
    """Utility function for preferred-timeslot constraints."""
    def __init__(
        self,
        task: DeliveryTask,
        penalty_coef: float = 1e-5
    ):
        self.task = task
        self._penalty_coef = penalty_coef

    def utility_function(self, x: dict[int, int]) -> float:
        """
        Args:
            x (dict[int, int]): Mapping from task ID to timeslot.
        Returns:
            float: Utility value (1 if in a preferred timeslot, otherwise 0).
        """
        assigned_timeslot = x[self.task.task_id]
        if assigned_timeslot in self.task.preferred_timeslots:
            utility = 1.0
        else:
            utility = 0.0

        # Penalty for tie-breaking.
        penalty = self.tie_breaking_function(x)
        return utility - self._penalty_coef * penalty

    def tie_breaking_function(self, x: dict[int, int]) -> float:
        """Compute the tie-breaking penalty."""
        assigned_timeslot = x[self.task.task_id]
        # Penalty based on task ID and assigned timeslot.
        penalty = self.task.task_id * assigned_timeslot
        return penalty

class WarehouseConflictUtility:
    """Utility function for warehouse-conflict constraints (multivariate)."""
    def __init__(
        self,
        warehouse_id: int,
        tasks: list[DeliveryTask],
        penalty_coef: float = 1e-5
    ):
        # Ensure all tasks use the same warehouse.
        for task in tasks:
            if task.warehouse_id != warehouse_id:
                raise ValueError(f"Task {task.task_id} does not use warehouse {warehouse_id}")

        self.warehouse_id = warehouse_id
        self.tasks = tasks
        self.task_ids = [task.task_id for task in tasks]
        self._penalty_coef = penalty_coef

    def utility_function(self, x: dict[int, int]) -> float:
        """
        Args:
            x (dict[int, int]): Mapping from task ID to timeslot.
        Returns:
            float: Utility value (1 when no conflicts, otherwise 0).
        """
        if len(self.tasks) <= 1:
            return 1.0  # No conflicts when there is one task or fewer.

        # Get assigned timeslots for each task.
        timeslots = [x[task_id] for task_id in self.task_ids]

        # Check whether duplicates exist.
        if len(set(timeslots)) != len(timeslots):
            utility = 0.0  # Conflict exists.
        else:
            utility = 1.0  # No conflict.

        penalty = self.tie_breaking_function(x)
        return utility - self._penalty_coef * penalty

    def tie_breaking_function(self, x: dict[int, int]) -> float:
        """Compute the tie-breaking penalty."""
        penalty = 0.0
        for task_id in self.task_ids:
            penalty += task_id * x[task_id]
        penalty /= len(self.task_ids)  # Normalization.
        return penalty

class AgentConflictUtility:
    """Utility function for agent-conflict constraints (multivariate)."""
    def __init__(
        self,
        agent_id: int,
        tasks: list[DeliveryTask],
        penalty_coef: float = 1e-5
    ):
        # Ensure all tasks belong to the same agent.
        for task in tasks:
            if task.agent_id != agent_id:
                raise ValueError(f"Task {task.task_id} does not belong to agent {agent_id}")

        self.agent_id = agent_id
        self.tasks = tasks
        self.task_ids = [task.task_id for task in tasks]
        self._penalty_coef = penalty_coef

    def utility_function(self, x: dict[int, int]) -> float:
        """
        Args:
            x (dict[int, int]): Mapping from task ID to timeslot.
        Returns:
            float: Utility value (1 when no conflicts, otherwise 0).
        """
        if len(self.tasks) <= 1:
            return 1.0  # No conflicts when there is one task or fewer.

        # Get assigned timeslots for each task.
        timeslots = [x[task_id] for task_id in self.task_ids]

        # Check whether duplicates exist.
        if len(set(timeslots)) != len(timeslots):
            utility = 0.0  # Conflict exists.
        else:
            utility = 1.0  # No conflict.

        penalty = self.tie_breaking_function(x)
        return utility - self._penalty_coef * penalty

    def tie_breaking_function(self, x: dict[int, int]) -> float:
        """Compute the tie-breaking penalty."""
        penalty = 0.0
        for task_id in self.task_ids:
            penalty += task_id * x[task_id]
        penalty /= len(self.task_ids)  # Normalization.
        return penalty

class DeliverySchedulingManager:
    """Manager class for the delivery-scheduling problem."""

    @classmethod
    def create_functions(
        cls,
        tasks: list[DeliveryTask],
        penalty_coef: float = 1e-5
    ) -> list[Function]:
        """
        Generate a list of utility functions from delivery tasks.

        Args:
            tasks: List of DeliveryTask instances.
            penalty_coef: Penalty coefficient for tie-breaking.

        Returns:
            list[Function]: List of utility functions.
        """
        functions = []
        func_id = 0

        # 1. Preferred-timeslot constraints (unary constraints).
        for task in tasks:
            utility_obj = PreferredTimeslotUtility(task, penalty_coef)
            func = Function(func_id, [task.task_id], utility_obj.utility_function)
            functions.append(func)
            func_id += 1

        # 2. Warehouse-conflict constraints (multivariate constraints).
        warehouse_tasks = {}
        for task in tasks:
            if task.warehouse_id not in warehouse_tasks:
                warehouse_tasks[task.warehouse_id] = []
            warehouse_tasks[task.warehouse_id].append(task)

        for warehouse_id, warehouse_task_list in warehouse_tasks.items():
            if len(warehouse_task_list) > 1:  # Create a constraint only when there are two or more tasks.
                utility_obj = WarehouseConflictUtility(warehouse_id, warehouse_task_list, penalty_coef)
                task_ids = [task.task_id for task in warehouse_task_list]
                func = Function(
                    func_id,
                    task_ids,
                    utility_obj.utility_function
                )
                functions.append(func)
                func_id += 1

        # 3. Agent-conflict constraints (multivariate constraints).
        agent_tasks = {}
        for task in tasks:
            if task.agent_id not in agent_tasks:
                agent_tasks[task.agent_id] = []
            agent_tasks[task.agent_id].append(task)

        for agent_id, agent_task_list in agent_tasks.items():
            if len(agent_task_list) > 1:  # Create a constraint only when there are two or more tasks.
                utility_obj = AgentConflictUtility(agent_id, agent_task_list, penalty_coef)
                task_ids = [task.task_id for task in agent_task_list]
                func = Function(
                    func_id,
                    task_ids,
                    utility_obj.utility_function
                )
                functions.append(func)
                func_id += 1

        return functions

    @classmethod
    def save_problem_instance(
        cls,
        tasks: list[DeliveryTask],
        path: pathlib.Path
    ):
        """Save a problem instance to a file."""
        data = []
        for task in tasks:
            data.append({
                'task_id': task.task_id,
                'agent_id': task.agent_id,
                'warehouse_id': task.warehouse_id,
                'preferred_timeslots': task.preferred_timeslots
            })
        with path.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_problem_instance(
        cls,
        path: pathlib.Path
    ) -> list[DeliveryTask]:
        """Load a problem instance from a file."""
        tasks = []
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                task = DeliveryTask(
                    item['task_id'],
                    item['agent_id'],
                    item['warehouse_id'],
                    item['preferred_timeslots']
                )
                tasks.append(task)
        return tasks

    @classmethod
    def get_constraint_violations(
        cls,
        tasks: list[DeliveryTask],
        assignment: dict[int, int]
    ) -> dict[str, int]:
        """Compute the number of constraint violations."""
        violations = {
            'preferred_timeslot': 0,
            'warehouse_conflict': 0,
            'agent_conflict': 0
        }

        # Preferred-timeslot constraint violations.
        for task in tasks:
            if assignment[task.task_id] not in task.preferred_timeslots:
                violations['preferred_timeslot'] += 1

        # Warehouse-conflict constraint violations.
        warehouse_assignments = {}
        for task in tasks:
            warehouse_id = task.warehouse_id
            timeslot = assignment[task.task_id]
            if warehouse_id not in warehouse_assignments:
                warehouse_assignments[warehouse_id] = {}
            if timeslot not in warehouse_assignments[warehouse_id]:
                warehouse_assignments[warehouse_id][timeslot] = []
            warehouse_assignments[warehouse_id][timeslot].append(task.task_id)

        for warehouse_id, timeslot_assignments in warehouse_assignments.items():
            for timeslot, task_ids in timeslot_assignments.items():
                if len(task_ids) > 1:
                    violations['warehouse_conflict'] += 1

        # Agent-conflict constraint violations.
        agent_assignments = {}
        for task in tasks:
            agent_id = task.agent_id
            timeslot = assignment[task.task_id]
            if agent_id not in agent_assignments:
                agent_assignments[agent_id] = {}
            if timeslot not in agent_assignments[agent_id]:
                agent_assignments[agent_id][timeslot] = []
            agent_assignments[agent_id][timeslot].append(task.task_id)

        for agent_id, timeslot_assignments in agent_assignments.items():
            for timeslot, task_ids in timeslot_assignments.items():
                if len(task_ids) > 1:
                    violations['agent_conflict'] += 1

        return violations

################
# Helper methods
################

def check_sat_solvability(tasks: list[DeliveryTask], timeslots_per_warehouse: int) -> bool:
    """
    Check whether a solution exists using a SAT solver.

    Args:
        tasks: List of DeliveryTask instances.
        timeslots_per_warehouse: Number of timeslots per warehouse.

    Returns:
        bool: True if a solution exists; otherwise False.
    """
    try:
        from pysat.formula import CNF
        from pysat.solvers import Solver
    except ImportError:
        print("SAT solver check is skipped because PySAT is not installed")
        return True

    # Variable mapping: task_id * timeslots_per_warehouse + timeslot + 1
    # (PySAT uses 1-based variable IDs.)
    cnf = CNF()

    # Assign at least one timeslot to each task.
    for task in tasks:
        clause = []
        for ts in range(timeslots_per_warehouse):
            var_id = task.task_id * timeslots_per_warehouse + ts + 1
            clause.append(var_id)
        cnf.append(clause)

    # Assign at most one timeslot to each task.
    for task in tasks:
        for ts1 in range(timeslots_per_warehouse):
            var_id1 = task.task_id * timeslots_per_warehouse + ts1 + 1
            for ts2 in range(ts1 + 1, timeslots_per_warehouse):
                var_id2 = task.task_id * timeslots_per_warehouse + ts2 + 1
                cnf.append([-var_id1, -var_id2])

    # Preferred-timeslot constraints.
    for task in tasks:
        for ts in range(timeslots_per_warehouse):
            if ts not in task.preferred_timeslots:
                var_id = task.task_id * timeslots_per_warehouse + ts + 1
                cnf.append([-var_id])

    # Warehouse-conflict constraints.
    warehouse_tasks = {}
    for task in tasks:
        if task.warehouse_id not in warehouse_tasks:
            warehouse_tasks[task.warehouse_id] = []
        warehouse_tasks[task.warehouse_id].append(task)

    for warehouse_id, warehouse_task_list in warehouse_tasks.items():
        for ts in range(timeslots_per_warehouse):
            for i in range(len(warehouse_task_list)):
                task_i = warehouse_task_list[i]
                var_id_i = task_i.task_id * timeslots_per_warehouse + ts + 1
                for j in range(i + 1, len(warehouse_task_list)):
                    task_j = warehouse_task_list[j]
                    var_id_j = task_j.task_id * timeslots_per_warehouse + ts + 1
                    cnf.append([-var_id_i, -var_id_j])

    # Agent-conflict constraints.
    agent_tasks = {}
    for task in tasks:
        if task.agent_id not in agent_tasks:
            agent_tasks[task.agent_id] = []
        agent_tasks[task.agent_id].append(task)

    for agent_id, agent_task_list in agent_tasks.items():
        for ts in range(timeslots_per_warehouse):
            for i in range(len(agent_task_list)):
                task_i = agent_task_list[i]
                var_id_i = task_i.task_id * timeslots_per_warehouse + ts + 1
                for j in range(i + 1, len(agent_task_list)):
                    task_j = agent_task_list[j]
                    var_id_j = task_j.task_id * timeslots_per_warehouse + ts + 1
                    cnf.append([-var_id_i, -var_id_j])

    # Check satisfiability with a SAT solver.
    with Solver(name='minisat22') as solver:
        solver.append_formula(cnf)
        return solver.solve()

def generate_random_instance(
    n_agents: int,
    tasks_per_agent: int,
    n_warehouses: int,
    timeslots_per_warehouse: int,
    min_preferred: int = 2,
    max_preferred: int = 6,
    check_sat: bool = False,
    max_attempts: int = 100
):
    """
    Generate a random delivery-scheduling problem instance.

    Args:
        n_agents: Number of agents.
        tasks_per_agent: Number of tasks per agent.
        n_warehouses: Number of warehouses.
        timeslots_per_warehouse: Number of timeslots per warehouse.
        min_preferred: Minimum number of preferred timeslots.
        max_preferred: Maximum number of preferred timeslots.

    Returns:
        list[DeliveryTask]: List of generated tasks.
    """
    for attempt in range(max_attempts):
        tasks = []
        task_id = 0

        for agent_id in range(n_agents):
            warehouse_ids = list(range(n_warehouses))
            random.shuffle(warehouse_ids)
            for t in range(tasks_per_agent):
                # Select a warehouse at random.
                warehouse_id = warehouse_ids[t]

                # Randomly determine the number of preferred timeslots.
                n_preferred = random.randint(min_preferred, max_preferred)
                preferred_timeslots = random.sample(
                    range(timeslots_per_warehouse),
                    min(n_preferred, timeslots_per_warehouse)
                )

                task = DeliveryTask(task_id, agent_id, warehouse_id, preferred_timeslots)
                tasks.append(task)
                task_id += 1

            # Check existence of a solution with a SAT solver.
        if not check_sat or check_sat_solvability(tasks, timeslots_per_warehouse):
            print(f"Found satisfiable instance after {attempt+1} attempts" if check_sat else "Generated instance")
            return tasks
        else:
            print(f"Attempt {attempt+1}: Generated instance is unsatisfiable, retrying...")

    print(f"Failed to find satisfiable instance after {max_attempts} attempts")
    return None

if __name__ == "__main__":
    SEED = 95939870
    INSTANCE_NUM = 50
    AGENT_NUMS = [12, 24, 36, 48]
    TASKS_PER_AGENT = 2
    TIMESLOTS_PER_WAREHOUSE = 8

    import random
    random.seed(SEED)

    manager = DeliverySchedulingManager()

    for n_agents in AGENT_NUMS:
        n_warehouses = n_agents // 2

        for i in range(INSTANCE_NUM):
            tasks = generate_random_instance(
                n_agents,
                TASKS_PER_AGENT,
                n_warehouses,
                TIMESLOTS_PER_WAREHOUSE,
                min_preferred=2,
                max_preferred=6,
                check_sat=True
            )
            if tasks is not None:
                parent_dir = pathlib.Path().parent  # current directory
                instance_dir = parent_dir / "delivery-scheduling" / f"n{n_agents}"
                instance_dir.mkdir(parents=True, exist_ok=True)
                instance_file = instance_dir / f"instance{i:02}.json"
                manager.save_problem_instance(tasks, instance_file)
