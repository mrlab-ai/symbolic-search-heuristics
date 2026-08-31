#!/bin/bash
#SBATCH --job-name=terminal-incidence-source-audit
#SBATCH --account=naiss2025-5-561-cpu
#SBATCH --partition=fat
#SBATCH --qos=normal
#SBATCH --array=0-45
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=8G
#SBATCH --time=00:30:00
#SBATCH --output=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb_terminal_incidence_source_audit_v3/slurm-%A_%a.out
#SBATCH --export=NONE

set -euo pipefail

unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONNOUSERSITE="1"
export PATH="/usr/bin:/bin"

cd /nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe
code_manifest="experiments/pdb_terminal_incidence_source_audit_code.sha256"
code_manifest_sha256="43ca650973b9016ec00fc90fa0400e8a3e1fb8b4d4df1975c3dc1b10a22dd4d4"
python_executable="/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb-terminal-incidence-shadow-venv/bin/python"
python_executable_sha256="021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
sha256sum_executable="/usr/bin/sha256sum"
sha256sum_executable_sha256="1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"

actual_sha256sum="$("${sha256sum_executable}" "${sha256sum_executable}")"
test "${actual_sha256sum%% *}" = "${sha256sum_executable_sha256}"
actual_python="$("${sha256sum_executable}" "${python_executable}")"
test "${actual_python%% *}" = "${python_executable_sha256}"
actual_manifest="$("${sha256sum_executable}" "${code_manifest}")"
test "${actual_manifest%% *}" = "${code_manifest_sha256}"
"${sha256sum_executable}" --strict --check "${code_manifest}"

exec "${python_executable}" \
    experiments/audit_pdb_terminal_incidence_sources.py scan \
    --output-dir experiments/data/pdb_terminal_incidence_source_audit_v3 \
    --num-shards 46 \
    --shard-index "${SLURM_ARRAY_TASK_ID}" \
    --code-manifest "${code_manifest}" \
    --code-manifest-sha256 "${code_manifest_sha256}"
