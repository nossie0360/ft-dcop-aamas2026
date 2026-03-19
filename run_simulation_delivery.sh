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
    problem_path="dcop/delivery-scheduling/n${node_num}/instance${graph_id}.json"
    output_path="out/simulation-${datetime}/delivery-scheduling/n${node_num}-b${fault_num}-k1-i${graph_id}/${algorithm}"
    log_path="log/simulation-${datetime}/delivery-scheduling/n${node_num}-b${fault_num}-k1-i${graph_id}/${algorithm}"

    # Create output directory
    mkdir -p "$(dirname "$output_path")"
    mkdir -p "$(dirname "$log_path")"

    # Run simulation
    echo "Running simulation:"
    echo "Algorithm: $algorithm"
    echo "Instance: $problem_path"
    echo "Fault num: $fault_num"

    python -m ft_dcop simulation \
        problem_type="delivery_scheduling" \
        algorithm="$algorithm" \
        problem_path="$problem_path" \
        fault_num="$fault_num" \
        fault_bound=1 \
        output_dir="$output_path" \
        log_dir="$log_path" \
        log_level="INFO" \
        create_timed_subdir="false"
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
            for fault_num in 0 $max_fault; do
                run_simulation $n_value $graph_id $algorithm $fault_num
            done
        done
    done
done
