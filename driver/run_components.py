import logging
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

from . import call
from . import limits
from . import portfolio_runner
from . import returncodes
from . import util
from . import __version__
from .plan_manager import PlanManager

if os.name == "posix":
    BINARY_EXT = ""
elif os.name == "nt":
    BINARY_EXT = ".exe"
else:
    returncodes.exit_with_driver_unsupported_error("Unsupported OS: " + os.name)

REL_TRANSLATE_PATH = Path("translate")
REL_PREPROCESS_PATH = f"preprocess{BINARY_EXT}"
REL_SEARCH_PATH = Path(f"downward{BINARY_EXT}")
_SEARCH_RESOURCE_LIMIT_EXITCODE_WITH_PLAN = {
    returncodes.SEARCH_OUT_OF_MEMORY:
        returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_MEMORY,
    returncodes.SEARCH_OUT_OF_TIME:
        returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_TIME,
    returncodes.SEARCH_OUT_OF_MEMORY_AND_TIME:
        returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_MEMORY_AND_TIME,
}
_SIGXCPU = getattr(signal, "SIGXCPU", None)
# Older versions of VAL use lower case, newer versions upper case. We prefer the
# older version because this is what our build instructions recommend.
_VALIDATE_NAME = (shutil.which(f"validate{BINARY_EXT}") or
                  shutil.which(f"Validate{BINARY_EXT}"))
VALIDATE = Path(_VALIDATE_NAME) if _VALIDATE_NAME else None


class IncompleteBuildError(Exception):
    pass


def _normalize_presearch_exitcode(exitcode):
    """Map a pre-search CPU-limit signal to the documented driver code.

    The translator and the legacy preprocessor run as child processes.  If
    either exhausts its RLIMIT_CPU allowance, ``subprocess`` reports
    ``-SIGXCPU``.  Passing that negative value through ``sys.exit`` would wrap
    it to an undocumented positive shell status (232 on POSIX), so normalize
    this one unambiguous resource outcome before the driver logs it.  Other
    signals remain distinguishable and fail closed as before.
    """
    if _SIGXCPU is not None and exitcode == -_SIGXCPU:
        return returncodes.TRANSLATE_OUT_OF_TIME
    return exitcode


def try_get_executable(build: str, rel_path: Path):
    build_dir = util.BUILDS_DIR / build / "bin"
    if not build_dir.exists():
        raise IncompleteBuildError(
            f"Could not find build '{build}' at {build_dir}.")

    path = build_dir / rel_path
    if not path.exists():
        raise IncompleteBuildError(
            f"Could not find '{rel_path}' in build '{build}'.")

    return path

def get_executable(build: str, rel_path: Path):
    try:
        return try_get_executable(build, rel_path)
    except IncompleteBuildError as err:
        returncodes.exit_with_driver_input_error(f"{err} Please run './build.py {build}'.")

def report_version(build: str):
    print(f"Fast Downward {__version__}")
    try:
        executable = try_get_executable(build, REL_SEARCH_PATH)
        search_git_revision = subprocess.check_output([executable, "--internal-git-revision"])
        print(f"git revision [{build}]: {search_git_revision.decode().strip()}")
    except IncompleteBuildError:
        print(f"git revision [{build}]: Build not found. Please run './build.py {build}'.")
    except subprocess.CalledProcessError as err:
        print(f"Cannot determine git revision of search binary. {err}")


def run_translate(args):
    logging.info("Running translator.")
    time_limit = limits.get_time_limit(
        args.translate_time_limit, args.overall_time_limit)
    memory_limit = limits.get_memory_limit(
        args.translate_memory_limit, args.overall_memory_limit)

    # Check existence of translate in build.
    translate = get_executable(args.build, REL_TRANSLATE_PATH)

    assert sys.executable, "Path to interpreter could not be found"
    cmd = [sys.executable] + ["-m", "translate"] + args.translate_inputs + args.translate_options

    stderr, returncode = call.get_error_output_and_returncode(
        "translator",
        cmd,
        time_limit=time_limit,
        memory_limit=memory_limit,
        prepend_to_python_path=translate.parent)
    returncode = _normalize_presearch_exitcode(returncode)

    # We collect stderr of the translator and print it here, unless
    # the translator ran out of memory and all output in stderr is
    # related to MemoryError.
    do_print_on_stderr = True
    if returncode == returncodes.TRANSLATE_OUT_OF_MEMORY:
        output_related_to_memory_error = True
        if not stderr:
            output_related_to_memory_error = False
        for line in stderr.splitlines():
            if "MemoryError" not in line:
                output_related_to_memory_error = False
                break
        if output_related_to_memory_error:
            do_print_on_stderr = False

    if do_print_on_stderr and stderr:
        returncodes.print_stderr(stderr)

    if returncode == 0:
        return (0, True)
    elif returncode == 1:
        # Unlikely case that the translator crashed without raising an
        # exception.
        return (returncodes.TRANSLATE_CRITICAL_ERROR, False)
    else:
        # Pass on any other exit code, including in particular signals or
        # exit codes such as running out of memory or time.
        return (returncode, False)


def run_preprocess(args):
    logging.info("Running preprocessor (%s)." % args.build)
    time_limit = limits.get_time_limit(
        args.preprocess_time_limit, args.overall_time_limit)
    memory_limit = limits.get_memory_limit(
        args.preprocess_memory_limit, args.overall_memory_limit)
    executable = get_executable(args.build, REL_PREPROCESS_PATH)
    try:
        call.check_call(
            "preprocess",
            [executable] + args.preprocess_options,
            stdin=args.preprocess_input,
            time_limit=time_limit,
            memory_limit=memory_limit)
    except subprocess.CalledProcessError as err:
        assert err.returncode >= 10 or err.returncode < 0, "got returncode < 10: {}".format(
            err.returncode)
        return (_normalize_presearch_exitcode(err.returncode), False)
    return (0, True)


def run_search(args):
    logging.info("Running search (%s)." % args.build)
    time_limit = limits.get_time_limit(
        args.search_time_limit, args.overall_time_limit)
    memory_limit = limits.get_memory_limit(
        args.search_memory_limit, args.overall_memory_limit)
    executable = get_executable(args.build, REL_SEARCH_PATH)

    plan_manager = PlanManager(
        args.plan_file,
        portfolio_bound=args.portfolio_bound,
        single_plan=args.portfolio_single_plan)
    plan_manager.delete_existing_plans()

    if args.portfolio:
        assert not args.search_options
        logging.info(f"search portfolio: {args.portfolio}")
        return portfolio_runner.run(
            args.portfolio, executable, args.search_input, plan_manager,
            time_limit, memory_limit)
    else:
        if not args.search_options:
            returncodes.exit_with_driver_input_error(
                "search needs --alias, --portfolio, or search options")
        if "--help" not in args.search_options:
            args.search_options.extend(["--internal-plan-file", args.plan_file])
        try:
            plan_artifacts_before_search = (
                plan_manager.get_plan_artifact_snapshot())
        except OSError:
            plan_artifacts_before_search = None
        try:
            call.check_call(
                "search",
                [executable] + args.search_options,
                stdin=args.search_input,
                time_limit=time_limit,
                memory_limit=memory_limit)
        except subprocess.CalledProcessError as err:
            raw_exitcode = err.returncode
        else:
            raw_exitcode = returncodes.SUCCESS

        print(f"search raw exit code: {raw_exitcode}", flush=True)
        if raw_exitcode == returncodes.SUCCESS:
            return (returncodes.SUCCESS, True)

        # The search binary does not directly return the driver's
        # SEARCH_PLAN_FOUND_AND_* codes. Negative exit codes are allowed for
        # passing out signals.
        assert raw_exitcode >= 10 or raw_exitcode < 0, \
            f"got returncode < 10: {raw_exitcode}"

        effective_exitcode = _SEARCH_RESOURCE_LIMIT_EXITCODE_WITH_PLAN.get(
            raw_exitcode)
        if (effective_exitcode is not None and
                plan_artifacts_before_search is not None):
            try:
                plan_artifacts_after_search = (
                    plan_manager.get_plan_artifact_snapshot())
            except OSError:
                plan_artifacts_after_search = None
            if plan_artifacts_after_search is not None:
                new_plan_artifacts = {
                    path: fingerprint
                    for path, fingerprint in
                    plan_artifacts_after_search.items()
                    if plan_artifacts_before_search.get(path) != fingerprint
                }
            else:
                new_plan_artifacts = {}
            if plan_manager.is_single_complete_plan(new_plan_artifacts):
                print(
                    "search resource-limit exit with complete plan: "
                    f"raw_exit_code={raw_exitcode} "
                    f"effective_exit_code={effective_exitcode}",
                    flush=True)
                return (effective_exitcode, True)

        return (raw_exitcode, False)


def run_validate(args):
    if not VALIDATE:
        returncodes.exit_with_driver_input_error(
            "Error: Trying to run validate but it was not found on the PATH.")

    logging.info("Running validate.")
    plan_files = list(PlanManager(args.plan_file).get_existing_plans())
    if not plan_files:
        print("Not running validate since no plans found.")
        return (0, True)

    try:
        call.check_call(
            "validate",
            [VALIDATE] + args.validate_inputs + plan_files,
            time_limit=args.validate_time_limit,
            memory_limit=args.validate_memory_limit)
    except OSError as err:
        returncodes.exit_with_driver_critical_error(err)
    else:
        return (0, True)
