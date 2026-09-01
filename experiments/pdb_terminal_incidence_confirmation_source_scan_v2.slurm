#!/bin/bash
#SBATCH --job-name=confirmation-source-audit-v2
#SBATCH --account=naiss2025-5-561-cpu
#SBATCH --partition=fat
#SBATCH --qos=normal
#SBATCH --array=0-819
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=256G
#SBATCH --time=01:40:00
#SBATCH --output=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb_terminal_incidence_confirmation_source_audit_v2/slurm-%A_%a.out
#SBATCH --export=NONE

set -euo pipefail

test "$#" -eq 2
source_inventory_sha256="$1"
source_audit_output_dir="$2"
[[ "${source_inventory_sha256}" =~ ^[0-9a-f]{64}$ ]]
[[ "${source_audit_output_dir}" = /* ]]

unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONNOUSERSITE="1"
export PYTHONDONTWRITEBYTECODE="1"
export PYTHONPYCACHEPREFIX="/tmp/symk-confirmation-source-audit-v2-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"
export PATH="/usr/bin:/bin"

cd /nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe
code_manifest="experiments/pdb_terminal_incidence_confirmation_source_audit_v2_code.sha256"
code_manifest_sha256="ecdb3789cf6000a7fda0a775ebadde809bb38b39c14040809eeeead6b2ba8e25"
source_inventory="experiments/data/pdb_terminal_incidence_confirmation_source_audit_v2/source-inventory-v2.json"
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
actual_inventory="$("${sha256sum_executable}" "${source_inventory}")"
test "${actual_inventory%% *}" = "${source_inventory_sha256}"
"${sha256sum_executable}" --strict --check "${code_manifest}"

exec "${python_executable}" -B \
    experiments/audit_pdb_terminal_incidence_confirmation_sources_v2.py scan \
    --output-dir "${source_audit_output_dir}" \
    --inventory-manifest "${source_inventory}" \
    --inventory-sha256 "${source_inventory_sha256}" \
    --num-shards 820 \
    --shard-index "${SLURM_ARRAY_TASK_ID}" \
    --task-timeout 2700 \
    --code-manifest "${code_manifest}" \
    --code-manifest-sha256 "${code_manifest_sha256}"
