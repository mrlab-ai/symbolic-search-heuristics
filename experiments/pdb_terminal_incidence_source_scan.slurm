#!/bin/bash
#SBATCH --job-name=terminal-incidence-source-audit
#SBATCH --account=naiss2025-5-561-cpu
#SBATCH --partition=fat
#SBATCH --qos=normal
#SBATCH --array=0-45
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=8G
#SBATCH --time=00:30:00
#SBATCH --output=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb_terminal_incidence_source_audit_v2/slurm-%A_%a.out

set -euo pipefail

cd /nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe
code_manifest="experiments/pdb_terminal_incidence_source_audit_code.sha256"
code_manifest_sha256="77325d690ed7b3ed04c53b4f62214976d3073581a0259a6d398e3e642ce14e37"
test "$(sha256sum "${code_manifest}" | cut -d' ' -f1)" = "${code_manifest_sha256}"
sha256sum --strict --check "${code_manifest}"

exec experiments/data/pdb-terminal-incidence-shadow-venv/bin/python \
    experiments/audit_pdb_terminal_incidence_sources.py scan \
    --output-dir experiments/data/pdb_terminal_incidence_source_audit_v2 \
    --num-shards 46 \
    --shard-index "${SLURM_ARRAY_TASK_ID}" \
    --code-manifest "${code_manifest}" \
    --code-manifest-sha256 "${code_manifest_sha256}"
