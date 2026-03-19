# FT-DCOP Simulation Code (AAMAS 2026)

## Overview

This repository contains the simulation code used in our paper published at [AAMAS2026](https://cyprusconferences.org/aamas2026/), which addresses fault tolerance in distributed constraint optimization problems (DCOPs).

Paper information:
> Koji Noshiro and Koji Hasebe, "Byzantine Fault Tolerance in Distributed Constraint Optimization Problems," 25th International Conference on Autonomous Agents and Multiagent Systems (AAMAS 2026), 9 pages, May. 2026.

Implemented algorithms in this codebase:
- Max-Sum (baseline)
- Repl-Max-Sum (proposed method)

Target problems:
- Graph Coloring
- Delivery Scheduling (Truck Appointment Scheduling, TAS)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Check base configuration:

- Main config file: `config/config.json`

## How To Run

There are two ways to run experiments.

### 1) Run comprehensive experiments with shell scripts

#### Graph Coloring

```bash
bash run_simulation_coloring.sh
```

This script runs experiments for:
- Algorithms: `max-sum`, `repl-max-sum`
- Number of agents: `12, 24, 36, 48`
- Problem instances: `graph00.csv` to `graph49.csv` (50 instances)
- Fault settings: `fault_num = (fault_factor * n) / 12` with `fault_factor in {0,1,2,3}`
- Fixed fault bound: `fault_bound = 1`

Output root pattern used by the script:
- `out/simulation-YYYYMMDD-HHMM/graph-coloring/...`

#### Delivery Scheduling (TAS)

```bash
bash run_simulation_delivery.sh
```

This script runs experiments for:
- Algorithms: `max-sum`, `repl-max-sum`
- Number of agents: `12, 24, 36, 48`
- Problem instances: `instance00.json` to `instance49.json` (50 instances)
- Fault settings: `fault_num in {0, n/3}`
- Fixed fault bound: `fault_bound = 1`

Output root pattern used by the script:
- `out/simulation-YYYYMMDD-HHMM/delivery-scheduling/...`

### 2) Run a single simulation from the module command

Basic format:

```bash
python -m ft_dcop simulation key1=value1 key2=value2 ...
```

Example (Graph Coloring, Max-Sum):

```bash
python -m ft_dcop simulation \
  algorithm=max-sum \
  problem_type=graph_coloring \
  problem_path=dcop/graph-coloring/n12/graph00.csv \
  fault_num=0 \
  fault_bound=1 \
  output_dir=out/manual \
  log_dir=log/manual
```

Example (Delivery Scheduling / TAS, Repl-Max-Sum):

```bash
python -m ft_dcop simulation \
  algorithm=repl-max-sum \
  problem_type=delivery_scheduling \
  problem_path=dcop/delivery-scheduling/n12/instance00.json \
  fault_num=4 \
  fault_bound=1 \
  output_dir=out/manual \
  log_dir=log/manual
```

Notes:
- Parameters are loaded from `config/config.json` first.
- Any `key=value` passed in the command line overrides the config value.
- For example, `algorithm=max-sum` overrides the `algorithm` field in the JSON config.

## Output Files (JSON)

For each simulation run, a JSON file is saved under:

- `<output_dir>/n<agents_num>/<problem_stem>_<algorithm>_b<fault_num>_k<fault_bound>.json`

Each output JSON contains two top-level blocks:
- `simulation_parameters`: effective parameters used in that run (after CLI overrides)
- `results`: summary metrics and detailed values

Main fields in `results`:
- `simulation_duration_sec`: wall-clock simulation time
- `total_message_count`: total number of exchanged messages
- `agents_num`: number of agents
- `actors_num`: number of actor instances (corresponding to variable/function nodes or their replicas) created in simulation
- `max_step`: maximum step count among non-faulty actors
- `max_runtime_sec`: maximum runtime among non-faulty actors
- `total_utility`: global objective value
- `conflict_count`: number of violated constraints
- `final_agent_values`: final assignment map (e.g., `agent_00`, `agent_01`, ...)
- `raw_results`: raw per-actor result tuples
