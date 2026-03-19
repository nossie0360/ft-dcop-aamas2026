from .constants import NODE_LIMIT, STR_VARIABLE, STR_FUNCTION
from .function import Function
from .node_alloc import NodeAlloc

def allocate_primary_backup_fixed_group(
    functions: list[Function],
    agents_num: int,
    backup_main_num: int,
    backup_sub_num: int,
    agent_variables_map: dict[int, list[int]] | None = None
) -> tuple[dict[int, NodeAlloc], dict[int, NodeAlloc]]:
    """
    Allocate agents to a primary and backups for variable and function nodes
    (allocating to fixed groups).

    Return:
        (alloc_variables: dict[int, NodeAlloc], alloc_functions: dict[int, NodeAlloc])
    """
    replica_num = 1 + backup_main_num + backup_sub_num
    if agent_variables_map is None:
        alloc_variables = {
            i: NodeAlloc(STR_VARIABLE, i, i, [], [], [i])
            for i in range(agents_num)
        }
    else:
        alloc_variables = {}
        for agent_id, variables in agent_variables_map.items():
            for var in variables:
                alloc_variables[var] = NodeAlloc(
                    STR_VARIABLE, var, agent_id, [], [], [var]
                )
    alloc_functions = {
        f.id + NODE_LIMIT: NodeAlloc(
            STR_FUNCTION, f.id + NODE_LIMIT, 0, [], [], f.variables
        )
        for f in functions
    }
    role_counts = {i: 0 for i in range(agents_num)}

    def get_candidates(prm: int, agt_num: int, rep_num: int):
        base = prm - prm % rep_num
        ret = [(prm + i) % rep_num + base for i in range(rep_num)]
        for i in range(rep_num):
            if ret[i] >= agt_num:
                ret[i] = ret[i] % agt_num + 1
        return ret

    for node_alloc in alloc_variables.values():
        candidates = get_candidates(node_alloc.primary, agents_num, replica_num)
        # node_alloc.primary = candidates[0]    # already assigned
        node_alloc.backup_main = [
            candidates[i] for i in range(1, 1 + backup_main_num)
        ]
        node_alloc.backup_sub = [
            candidates[i] for i in range(1 + backup_main_num, replica_num)
        ]
        for c in candidates:
            role_counts[c] += 1
    for func in sorted(functions, key=lambda x:min(x.variables), reverse=True): # Greedy load balancing
        fid = func.id + NODE_LIMIT
        if agent_variables_map is None:
            related_agents = func.variables
        else:
            related_agents = set()
            for agt, vars in agent_variables_map.items():
                if set(vars) & set(func.variables):
                    related_agents.add(agt)
        var_role_counts = {
            k: v for k, v in role_counts.items()
            if k in related_agents
        }
        primary = min(var_role_counts, key=var_role_counts.get)
        candidates = get_candidates(primary, agents_num, replica_num)
        alloc_functions[fid].primary = candidates[0]
        alloc_functions[fid].backup_main = [
            candidates[i]
            for i in range(1, 1 + backup_main_num)
        ]
        alloc_functions[fid].backup_sub = [
            candidates[i]
            for i in range(1 + backup_main_num, replica_num)
        ]
        for c in candidates:
            role_counts[c] += 1
    return alloc_variables, alloc_functions
