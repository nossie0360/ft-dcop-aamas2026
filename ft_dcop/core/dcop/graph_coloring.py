import pathlib

from ..common.function import Function

class GraphColoringEdgeUtility:
    def __init__(
        self,
        node_i_id: int,
        node_j_id: int,
        node_i_degree: int,
        node_j_degree: int,
        graph_node_num: int,
        graph_edge_num: int,
        penalty_coef: float = 1e-5,
        default_value: int = 0,
        ignore_default_value: bool = False
    ):
        """Initializes the utility for a single edge in a graph coloring problem.

        Args:
            node_i_id (int): The ID of the first node of the edge.
            node_j_id (int): The ID of the second node of the edge.
            node_i_degree (int): The degree of the first node.
            node_j_degree (int): The degree of the second node.
            graph_node_num (int): The total number of nodes in the graph.
            graph_edge_num (int): The total number of edges in the graph.
            penalty_coef (float, optional): The coefficient for the tie-breaking penalty.
                Defaults to 1e-5.
            default_value (int, optional): The value indicating a default or unassigned state.
                Defaults to 0.
            ignore_default_value (bool, optional): If True, the utility will be 0 if
                either node has the default_value.
                Defaults to False.
        """
        self._node_i_id = node_i_id
        self._node_j_id = node_j_id
        self._node_i_degree = node_i_degree
        self._node_j_degree = node_j_degree
        self._graph_node_num = graph_node_num
        self._graph_edge_num = graph_edge_num
        self._penalty_coef = penalty_coef
        self._default_value = default_value
        self._ignore_default_value = ignore_default_value

    def utility_function(self, x: dict[int, int]) -> float:
        """Calculates the utility for an edge based on the assigned colors.

        The utility is 1 if the colors are different, and 0 if they are the same
        or if one of the nodes has a default value. A tie-breaking penalty is
        subtracted.

        Args:
            x (dict[int, int]): A dictionary mapping node IDs to their assigned colors.

        Returns:
            float: The calculated utility for the edge.
        """
        val_i = x[self._node_i_id]
        val_j = x[self._node_j_id]
        if (
            self._ignore_default_value
            and (val_i == self._default_value or val_j == self._default_value)
        ):
            edge_util = 0
        elif val_i == val_j:
            edge_util = 0
        else:
            edge_util = 1
        penalty = self.tie_breaking_function(x)
        util = edge_util - self._penalty_coef * penalty
        return util

    def tie_breaking_function(self, x: dict[int, int]) -> float:
        """Calculates a penalty for tie-breaking.

        This function provides a deterministic way to choose between solutions
        with the same utility, based on node IDs and their assigned colors.
        Each node's preference is normalized by its degree to avoid over-counting
        for high-degree nodes.

        Args:
            x (dict[int, int]): A dictionary mapping node IDs to their assigned colors.

        Returns:
            float: The calculated penalty value.
        """
        val_i = x[self._node_i_id]
        val_j = x[self._node_j_id]
        # Each node's preference contribution is normalized by its degree
        penalty = (
            (self._graph_node_num - self._node_i_id) * val_i / self._node_i_degree
            + (self._graph_node_num - self._node_j_id) * val_j / self._node_j_degree
        )
        return penalty

class GraphColoringManager:
    @classmethod
    def generate_functions_from_adjlist_file(
        cls,
        path: pathlib.Path,
        penalty_coef: float = 1e-5,
        default_value: int = 0
    ) -> list[Function]:
        """Generates utility functions from a graph defined in an adjlist file.

        The file format should be one line per node, with the node and its
        neighbors separated by commas. e.g., "node,neighbor1,neighbor2,..."

        Args:
            path (pathlib.Path): The path to the adjlist file.
            penalty_coef (float, optional): The coefficient for the tie-breaking penalty.
                Defaults to 1e-5.
            default_value (int, optional): The value indicating a default or unassigned state.
                Defaults to 0.

        Raises:
            RuntimeError: If there is an error reading or parsing the file.

        Returns:
            list[Function]: A list of Function objects representing the utility of each edge.
        """
        graph_node_num = 0
        edges = set()
        node_degrees = {}  # Track the degree of each node

        try:
            with path.open('r', encoding='utf-8') as f:
                for line in f:
                    # Ignore comments
                    if line.startswith('#'):
                        continue
                    # Remove spaces etc.
                    line = line.strip()
                    if not line:
                        continue

                    # Format: node,neighbor1,neighbor2,...
                    # Assume that labels are integers
                    node_strs = line.split(",")
                    nodes = [int(n.strip()) for n in node_strs if n.strip()]
                    if not nodes:
                        continue
                    graph_node_num += 1

                    # Add edges and count degrees
                    source_node = nodes[0]
                    for neighbor in nodes[1:]:
                        edge = tuple(sorted((source_node, neighbor)))
                        if edge not in edges:  # Only count each edge once
                            edges.add(edge)
                            # Increment degree for both nodes
                            node_degrees[source_node] = node_degrees.get(source_node, 0) + 1
                            node_degrees[neighbor] = node_degrees.get(neighbor, 0) + 1
        except Exception as e:
            raise RuntimeError(f"Error reading or parsing adjlist file {path}: {e}") from e

        functions = []
        graph_edge_num = len(edges)
        for i, (node_i, node_j) in enumerate(sorted(list(edges))):
            utility_obj = GraphColoringEdgeUtility(
                node_i,
                node_j,
                node_degrees[node_i],
                node_degrees[node_j],
                graph_node_num,
                graph_edge_num,
                penalty_coef=penalty_coef,
                default_value=default_value,
                ignore_default_value=False
            )
            func = Function(i, [node_i, node_j], utility_obj.utility_function)
            functions.append(func)

        return functions

    @classmethod
    def get_conflict_counts(
        cls,
        functions: list[Function],
        x: dict[int, int],
        default_value: int = 0,
        ignore_default_value: bool = False
    ) -> int:
        """Calculates the number of conflicts (edges with same-colored endpoints)
        for a given graph coloring.

        Args:
            functions (list[Function]): The list of utility functions for the graph.
                                        Each function is assumed to represent an edge.
            x (dict[int, int]): A dictionary mapping node IDs to their assigned colors.
            default_value (int, optional): The value considered as 'unassigned' or 'default'.
                                           Defaults to 0.
            ignore_default_value (bool, optional): If True, edges where at least one
                                                   endpoint has the default_value are
                                                   ignored when counting conflicts.
                                                   Defaults to False.

        Returns:
            int: The total number of conflicts.
        """
        conflicts = 0
        for f in functions:
            if len(f.variables) != 2:
                raise ValueError("Function must have exactly two variables for conflict calculation.")

            node_i = f.variables[0]
            node_j = f.variables[1]
            val_i = x[node_i]
            val_j = x[node_j]

            # If ignore_default_value is True, and either value is default, skip conflict check
            if ignore_default_value and (val_i == default_value or val_j == default_value):
                continue

            # If values are not default and are the same, it's a conflict
            if val_i == val_j:
                conflicts += 1

        return conflicts


################
# Helper methods
################

def generate_graphs():
    """Generates random graph files for graph coloring problems.

    This function creates a set of graph instances with specified parameters
    (node count, mean degree) and saves them as adjacency list files.
    It ensures that the generated graphs are connected and can be colored
    with a specific number of colors.
    """
    SEED = 95939870
    INSTANCE_NUM = 50
    COLOR_NUM = 3
    MEAN_DEGREE = 3
    NODE_NUMS = [12, 24, 36, 48]

    import random
    import numpy as np
    import networkx as nx
    from pathlib import Path

    random.seed(SEED)
    np.random.seed(SEED)
    parent_dir = Path().parent # current directory
    for node_num in NODE_NUMS:
        instance_dir = parent_dir / "graph-coloring" / f"n{node_num}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        for i in range(INSTANCE_NUM):
            while True:
                edge_num = MEAN_DEGREE * node_num / 2
                graph: nx.Graph = nx.gnm_random_graph(node_num, edge_num)
                degrees = [x[1] for x in graph.degree]
                if min(degrees) > 0:    # retry if the minimum degree is 0
                    color_dict = nx.greedy_color(graph)
                    if len(set(color_dict.values())) == COLOR_NUM:  # retry if not colorable
                        break
            graph_file = instance_dir / f"graph{i:02}.csv"
            nx.write_adjlist(graph, graph_file, delimiter=",")
    seed_file = parent_dir / "graph-coloring" / "seed.txt"
    seed_file.write_text(f"SEED={SEED}")


if __name__ == "__main__":
    generate_graphs()
