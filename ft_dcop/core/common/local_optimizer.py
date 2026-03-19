import numpy as np
import numpy.typing as npt


from .function import Function

class LocalOptimizer:
    def __init__(self, variables: list[int], domains: dict[int, list[int]]):
        # Store initial parameters
        self.variables = variables
        self.domains = domains

        # Create index to value mappings
        self.idx_to_value = {var: np.array(domains[var]) for var in variables}

        # Create shape for function table
        self.domain_sizes = [len(domains[var]) for var in variables]
        self.func_table = None

    def update_function_table(self, variables: list[int],
                              domains: dict[int, list[int]],
                              func: Function) -> None:
        """Precompute all function values and store in table"""
        # Update parameters
        self.variables = variables
        self.domains = domains

        # Update the mapping and the size of the domain
        self.idx_to_value = {var: np.array(domains[var]) for var in variables}
        self.domain_sizes = [len(domains[var]) for var in variables]

        # Create grid of all possible value combinations
        domain_arrays = [self.idx_to_value[var] for var in self.variables]
        grid = np.meshgrid(*domain_arrays, indexing='ij')

        # Create function value table
        self.func_table = np.zeros(self.domain_sizes)
        grid_flat = [g.flatten() for g in grid]
        value_dicts = [{self.variables[j]: grid_flat[j][i]
                        for j in range(len(self.variables))}
                       for i in range(len(grid_flat[0]))]

        # Fill table with function values
        self.func_table.flat = [func.function(vd) for vd in value_dicts]

    def optimize_for_variable(self, q_function: list[npt.NDArray],
                              target_var: int) -> npt.NDArray:
        """Optimize for target variable using precomputed function table"""
        if self.func_table is None:
            raise ValueError("Function table not prepared. Call update_function_table first.")

        target_idx = self.variables.index(target_var)

        # Sum all q_functions except target
        q_sum = np.zeros(self.domain_sizes)
        for i, q in enumerate(q_function):
            if i != target_idx:
                # Create slice object for broadcasting
                broadcast_shape = [1] * len(self.domain_sizes)
                broadcast_shape[i] = -1
                q_reshaped = q.reshape(broadcast_shape)
                q_sum += q_reshaped

        # Calculate total utility
        total_utils = q_sum + self.func_table

        # Maximize over all dimensions except target
        axes = tuple(i for i in range(len(self.domain_sizes)) if i != target_idx)
        ret_array = np.amax(total_utils, axis=axes)

        return ret_array
