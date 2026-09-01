#!/bin/bash

set -euo pipefail

test "$#" -eq 0
source_inventory_sha256="bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
source_audit_output_dir="/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb_terminal_incidence_confirmation_source_audit_v6_repair"
task_timeout_seconds="__V6_TASK_TIMEOUT_SECONDS__"
[[ "${task_timeout_seconds}" =~ ^(28800|115200)$ ]]
[[ "${SLURM_ARRAY_JOB_ID}" =~ ^[0-9]+$ ]]
[[ "${SLURM_ARRAY_TASK_ID}" =~ ^[0-9]+$ ]]
test "${SLURM_ARRAY_TASK_ID}" -ge 0
test "${SLURM_ARRAY_TASK_ID}" -lt 820

unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONNOUSERSITE="1"
export PYTHONDONTWRITEBYTECODE="1"
export PATH="/usr/bin:/bin"

cd /nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe
code_manifest="experiments/pdb_terminal_incidence_confirmation_source_audit_v6_code.sha256"
code_manifest_sha256="__V6_CODE_MANIFEST_SHA256__"
source_inventory="experiments/data/pdb_terminal_incidence_confirmation_source_audit_v6_repair/source-inventory-v6.json"
tmpdir_root="/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb_terminal_incidence_confirmation_source_audit_v6_tmp"
python_executable="/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb-terminal-incidence-shadow-venv/bin/python"
python_executable_sha256="021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
sha256sum_executable="/usr/bin/sha256sum"
sha256sum_executable_sha256="1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
mkdir_executable="/usr/bin/mkdir"
mkdir_executable_sha256="9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
rmdir_executable="/usr/bin/rmdir"
rmdir_executable_sha256="b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"

actual_sha256sum="$("${sha256sum_executable}" "${sha256sum_executable}")"
test "${actual_sha256sum%% *}" = "${sha256sum_executable_sha256}"
actual_python="$("${sha256sum_executable}" "${python_executable}")"
test "${actual_python%% *}" = "${python_executable_sha256}"
actual_mkdir="$("${sha256sum_executable}" "${mkdir_executable}")"
test "${actual_mkdir%% *}" = "${mkdir_executable_sha256}"
actual_rmdir="$("${sha256sum_executable}" "${rmdir_executable}")"
test "${actual_rmdir%% *}" = "${rmdir_executable_sha256}"
actual_manifest="$("${sha256sum_executable}" "${code_manifest}")"
test "${actual_manifest%% *}" = "${code_manifest_sha256}"
actual_inventory="$("${sha256sum_executable}" "${source_inventory}")"
test "${actual_inventory%% *}" = "${source_inventory_sha256}"
"${sha256sum_executable}" --strict --check "${code_manifest}"

test -d "${tmpdir_root}"
test ! -L "${tmpdir_root}"
export TMPDIR="${tmpdir_root}/task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"
export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"
test ! -e "${TMPDIR}"
umask 077
"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"

cleanup_tmpdir() {
    status="$?"
    trap - EXIT
    if ! "${rmdir_executable}" -- "${TMPDIR}"; then
        exit 97
    fi
    exit "${status}"
}
trap cleanup_tmpdir EXIT

"${python_executable}" -B \
    experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py scan \
    --output-dir "${source_audit_output_dir}" \
    --inventory-manifest "${source_inventory}" \
    --inventory-sha256 "${source_inventory_sha256}" \
    --num-shards 820 \
    --shard-index "${SLURM_ARRAY_TASK_ID}" \
    --task-timeout "${task_timeout_seconds}" \
    --code-manifest "${code_manifest}" \
    --code-manifest-sha256 "${code_manifest_sha256}"
