#!/bin/bash
#SBATCH --account=naiss2025-5-561-cpu
#SBATCH --partition=fat
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=26G
#SBATCH --time=01:10:00
#SBATCH --array=0-0
#SBATCH --output=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb-terminal-incidence-confirmation-source-audit-v12-canary-logs/slurm-%A_%a.out
#SBATCH --error=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/experiments/data/pdb-terminal-incidence-confirmation-source-audit-v12-canary-logs/slurm-%A_%a.err
#SBATCH --export=NONE
#SBATCH --nice=0
#SBATCH --no-requeue

set -euo pipefail

test "$#" -eq 0
[[ "${SLURM_ARRAY_JOB_ID}" =~ ^[0-9]+$ ]]
[[ "${SLURM_ARRAY_TASK_ID}" =~ ^[0-9]+$ ]]
test "${SLURM_ARRAY_TASK_ID}" -ge 0
test "${SLURM_ARRAY_TASK_ID}" -eq 0

unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONNOUSERSITE="1"
export PYTHONDONTWRITEBYTECODE="1"
export LANG="C"
export LC_ALL="C"
export PATH="/usr/bin:/bin"

repo="/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe"
output_dir="${repo}/experiments/data/pdb-terminal-incidence-confirmation-source-audit-v12-canary"
tmp_root="${repo}/experiments/data/pdb-terminal-incidence-confirmation-source-audit-v12-canary-tmp"
log_root="${repo}/experiments/data/pdb-terminal-incidence-confirmation-source-audit-v12-canary-logs"
code_manifest="${repo}/experiments/pdb_terminal_incidence_confirmation_source_audit_v12_code.sha256"
code_manifest_sha256="__V12_CODE_MANIFEST_SHA256__"
repository_commit_id="__V12_REPOSITORY_COMMIT_ID__"
python_executable="/home/jendrik/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
python_executable_sha256="021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
sha256sum_executable="/usr/bin/sha256sum"
sha256sum_executable_sha256="1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
mkdir_executable="/usr/bin/mkdir"
mkdir_executable_sha256="9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
rmdir_executable="/usr/bin/rmdir"
rmdir_executable_sha256="b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"

cd "${repo}"
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
"${sha256sum_executable}" --strict --check "${code_manifest}"

test -d "${output_dir}"
test ! -L "${output_dir}"
test -d "${tmp_root}"
test ! -L "${tmp_root}"
test -d "${log_root}"
test ! -L "${log_root}"
export TMPDIR="${tmp_root}/task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"
export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"
test ! -e "${TMPDIR}"
umask 077
"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"

cleanup_tmpdir() {
    status="$?"
    trap - EXIT
    if test "${status}" -eq 0; then
        if ! "${rmdir_executable}" -- "${TMPDIR}"; then
            exit 97
        fi
    fi
    exit "${status}"
}
trap cleanup_tmpdir EXIT

"${python_executable}" -B \
    experiments/audit_pdb_terminal_incidence_confirmation_sources_v12.py compute-canary \
    --output-dir "${output_dir}" \
    --code-manifest "${code_manifest}" \
    --code-manifest-sha256 "${code_manifest_sha256}" \
    --repository-commit-id "${repository_commit_id}" \
    --tmp-root "${tmp_root}"
