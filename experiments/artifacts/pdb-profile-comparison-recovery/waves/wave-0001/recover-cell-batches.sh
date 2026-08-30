#!/bin/bash -l
#SBATCH --job-name=pdbprof-b01-39e084c54a13
#SBATCH --output=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-cap-grid-results/experiments/artifacts/pdb-profile-comparison-recovery/waves/wave-0001/recovery-batch-slurm-%A_%a.log
#SBATCH --error=/nobackup/proj/disk/dfsplan/personal/jendrik/symk-cap-grid-results/experiments/artifacts/pdb-profile-comparison-recovery/waves/wave-0001/recovery-batch-slurm-%A_%a.err
#SBATCH --open-mode=append
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --time=02:30:00
#SBATCH --mem-per-cpu=9G
#SBATCH --cpus-per-task=2
#SBATCH --array=1-566%2
#SBATCH --account=naiss2025-5-561-cpu
#SBATCH --no-requeue

set -euo pipefail
LEGACY_RUNNER='/nobackup/proj/disk/dfsplan/personal/jendrik/symk-cap-grid-results/experiments/artifacts/pdb-profile-comparison-recovery/waves/wave-0001/recover-cells.sh'
LEGACY_RUNNER_SHA256=793a3d86cd3b20db5629018a08968b7f1a599b2a1684be06039940d95648f4d8
SRUN='/usr/bin/srun'
SRUN_SHA256=6bd4276fb1d7c70bf2cdb4997a224c4b7a231a71c9cf424e25300d292dd0522c
ENV='/usr/bin/env'
ENV_SHA256=4fa9935734560713b5a6250fa3481d1044ad117f220bf32c802af382bb7e5c9b
LEGACY_TASKS=1132
CELLS_PER_ARRAY_TASK=2

fail() {
    printf '%s\n' "$1" >&2
    exit 2
}

require_executable() {
    local path=$1
    local expected=$2
    [[ -f "$path" && ! -L "$path" && -x "$path" ]] || fail "sealed executable changed: $path"
    local actual
    actual=$(sha256sum -- "$path") || fail "cannot hash sealed executable: $path"
    actual=${actual%% *}
    [[ "$actual" == "$expected" ]] || fail "sealed executable hash changed: $path"
}

attest_batch_inputs() {
    require_executable "$LEGACY_RUNNER" "$LEGACY_RUNNER_SHA256"
    require_executable "$SRUN" "$SRUN_SHA256"
    require_executable "$ENV" "$ENV_SHA256"
}

attest_batch_inputs
ARRAY_TASKS=566
[[ $SLURM_ARRAY_TASK_ID =~ ^[1-9][0-9]*$ ]] || fail 'invalid batched recovery array index'
if (( ${#SLURM_ARRAY_TASK_ID} > ${#ARRAY_TASKS} )); then
    fail 'batched recovery array index is outside the sealed array range'
fi
if (( ${#SLURM_ARRAY_TASK_ID} == ${#ARRAY_TASKS} ))     && [[ "$SLURM_ARRAY_TASK_ID" > "$ARRAY_TASKS" ]]; then
    fail 'batched recovery array index is outside the sealed array range'
fi
FIRST=$(( (SLURM_ARRAY_TASK_ID - 1) * CELLS_PER_ARRAY_TASK + 1 ))
LAST=$(( FIRST + CELLS_PER_ARRAY_TASK - 1 ))
if [[ $FIRST -lt 1 || $FIRST -gt $LEGACY_TASKS ]]; then
    fail 'batched recovery array index is outside the sealed cell set'
fi
if [[ $LAST -gt $LEGACY_TASKS ]]; then
    LAST=$LEGACY_TASKS
fi
PIDS=()
for ((LEGACY_TASK=FIRST; LEGACY_TASK<=LAST; LEGACY_TASK++)); do
    (
        exec "$SRUN" --exclusive --exact --nodes=1 --ntasks=1             --cpus-per-task=1 --mem-per-cpu=9G --export=ALL             "$ENV" "SLURM_ARRAY_TASK_ID=$LEGACY_TASK" "$LEGACY_RUNNER"
    ) &
    PIDS+=("$!")
done
STATUS=0
for PID in "${PIDS[@]}"; do
    if wait "$PID"; then
        :
    else
        RETCODE=$?
        if [[ $STATUS -eq 0 ]]; then
            STATUS=$RETCODE
        fi
    fi
done
attest_batch_inputs
exit "$STATUS"
