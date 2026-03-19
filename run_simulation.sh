#!/bin/bash

# Get current datetime (YYYYMMDD-HHMM format)
datetime=$(date '+%Y%m%d-%H%M')

# Array of algorithms
algorithms=("max-sum" "repl-max-sum")

# Function to run simulation
run_simulation() {
    local node_num=$1
    local graph_id=$2
    local algorithm=$3
    local fault_num=$4

    # Create paths
    problem_path="dcop/graph-coloring/n${node_num}/graph${graph_id}.csv"
    output_path="out/simulation-${datetime}/graph-coloring/n${node_num}-b${fault_num}-k1-g${graph_id}/${algorithm}"
    log_path="log/simulation-${datetime}/graph-coloring/n${node_num}-b${fault_num}-k1-g${graph_id}/${algorithm}"

    # Create output directory
    mkdir -p "$(dirname "$output_path")"
    mkdir -p "$(dirname "$log_path")"

    # Run simulation
    echo "Running simulation:"
    echo "Algorithm: $algorithm"
    echo "Graph: $problem_path"
    echo "Fault num: $fault_num"

    python -m ft_dcop simulation \
        algorithm="$algorithm" \
        problem_path="$problem_path" \
        fault_num="$fault_num" \
        fault_bound=1 \
        output_dir="$output_path" \
        log_dir="$log_path" \
        log_level="INFO" \
        create_timed_subdir="false" \
        damping_factor=0.9
}

# Main execution loop
for n_value in 12 24 36 48; do
    # Set maximum fault-num based on the number of agents
    max_fault=$((n_value / 3))
    # Execute for each problem
    for graph_id in $(seq -w 0 49); do
        # Execute for each algorithm
        for algorithm in "${algorithms[@]}"; do
            # Execute for each fault-num
            for fault_num in $max_fault; do
                run_simulation $n_value $graph_id $algorithm $fault_num
            done
        done
    done
done
