import itertools
import os
from pathlib import Path
import re
import stat

from . import returncodes


_PLAN_INFO_REGEX = re.compile(r"; cost = (\d+) \((unit cost|general cost)\)\n")


def _parse_plan_stream(input_file):
    """Parse a plan stream with exactly one canonical final cost footer."""
    line = None
    footer = None
    footer_count = 0
    for line in input_file:
        match = _PLAN_INFO_REGEX.fullmatch(line)
        if match:
            footer = match
            footer_count += 1
    if footer_count == 1 and footer is not None:
        final_match = _PLAN_INFO_REGEX.fullmatch(line or "")
        if final_match:
            return int(final_match.group(1)), final_match.group(2)
    return None, None


def _parse_plan(plan_path: Path):
    """Parse a plan file and return a pair (cost, problem_type)
    summarizing the salient information. Return (None, None) for
    incomplete plans."""
    with plan_path.open() as input_file:
        return _parse_plan_stream(input_file)


def _get_file_fingerprint(status):
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns)


class PlanManager:
    def __init__(self, plan_prefix: Path, portfolio_bound=None, single_plan=False):
        self._plan_prefix = plan_prefix
        self._plan_costs = []
        self._problem_type = None
        if portfolio_bound is None:
            portfolio_bound = "infinity"
        self._portfolio_bound = portfolio_bound
        self._single_plan = single_plan

    def get_plan_prefix(self):
        return self._plan_prefix

    def get_plan_counter(self):
        return len(self._plan_costs)

    def get_next_portfolio_cost_bound(self):
        """Return the next plan cost bound to be used in a portfolio planner.

        Initially, this is the user-specified cost bound, or "infinity"
        if the user specified no bound. Once a plan has been found, it
        is the cost of the best plan found so far. (This is always the
        last plan found because plans must decrease in cost.)
        """
        if self._plan_costs:
            return self._plan_costs[-1]
        else:
            return self._portfolio_bound

    def abort_portfolio_after_first_plan(self):
        return self._single_plan

    def get_problem_type(self):
        if self._problem_type is None:
            returncodes.exit_with_driver_critical_error("no plans found yet: cost type not set")
        return self._problem_type

    def process_new_plans(self):
        """Update information about plans after a planner run.

        Read newly generated plans and store the relevant information.
        If the last plan file is incomplete, delete it.
        """
        had_incomplete_plan = False
        for counter in itertools.count(self.get_plan_counter() + 1):
            plan_path = self._get_plan_path(counter)
            def bogus_plan(msg):
                returncodes.exit_with_driver_critical_error(f"{str(plan_path)}: {msg}")
            if not plan_path.exists():
                break
            if had_incomplete_plan:
                bogus_plan("plan found after incomplete plan")
            cost, problem_type = _parse_plan(plan_path)
            if cost is None:
                had_incomplete_plan = True
                print(f"{plan_path} is incomplete. Deleted the file.")
                plan_path.unlink()
            else:
                print(f"plan manager: found new plan with cost {cost}")
                if self._problem_type is None:
                    # This is the first plan we found.
                    self._problem_type = problem_type
                else:
                    # Check if info from this plan matches previous info.
                    if self._problem_type != problem_type:
                        bogus_plan("problem type has changed")
                    if cost >= self._plan_costs[-1]:
                        bogus_plan("plan quality has not improved")
                self._plan_costs.append(cost)

    def get_existing_plans(self):
        """Yield all plans that match the given plan prefix."""
        if self._plan_prefix.exists():
            yield self._plan_prefix

        for counter in itertools.count(start=1):
            plan_path = self._get_plan_path(counter)
            if plan_path.exists():
                yield plan_path
            else:
                break

    def get_existing_plan_artifacts(self):
        """Return existing entries that use the plan-file naming scheme.

        In contrast to get_existing_plans(), this also finds broken symlinks,
        nonregular entries, and numbered entries after a gap. This stricter
        inventory is used when deciding whether a direct search produced
        exactly one trustworthy plan file.
        """
        artifacts = []
        if self._plan_prefix.exists() or self._plan_prefix.is_symlink():
            artifacts.append(self._plan_prefix)

        parent = self._plan_prefix.parent
        numbered_prefix = f"{self._plan_prefix.name}."
        for path in parent.iterdir():
            if not path.name.startswith(numbered_prefix):
                continue
            suffix = path.name[len(numbered_prefix):]
            if suffix.isdigit():
                artifacts.append(path)
        return sorted(artifacts, key=str)

    def get_plan_artifact_snapshot(self):
        """Return fingerprints for all currently existing plan artifacts."""
        snapshot = {}
        for path in self.get_existing_plan_artifacts():
            snapshot[path] = _get_file_fingerprint(path.lstat())
        return snapshot

    def is_single_complete_plan(self, plan_artifacts):
        """Return whether artifacts contain one valid direct-search plan."""
        if list(plan_artifacts) != [self._plan_prefix]:
            return False

        expected_fingerprint = plan_artifacts[self._plan_prefix]
        expected_mode = expected_fingerprint[2]
        expected_nlink = expected_fingerprint[3]
        if not stat.S_ISREG(expected_mode) or expected_nlink != 1:
            return False

        flags = os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        descriptor = None
        try:
            descriptor = os.open(self._plan_prefix, flags)
            if (_get_file_fingerprint(os.fstat(descriptor)) !=
                    expected_fingerprint):
                return False
            with os.fdopen(descriptor) as input_file:
                descriptor = None
                cost, problem_type = _parse_plan_stream(input_file)
                if (_get_file_fingerprint(os.fstat(input_file.fileno())) !=
                        expected_fingerprint):
                    return False
            if (_get_file_fingerprint(self._plan_prefix.lstat()) !=
                    expected_fingerprint):
                return False
        except (OSError, UnicodeError):
            return False
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return cost is not None and problem_type is not None

    def delete_existing_plans(self):
        """Delete all plans that match the given plan prefix."""
        for plan in self.get_existing_plans():
            plan.unlink()

    def _get_plan_path(self, number):
        return Path(f"{(self._plan_prefix)}.{number}")
