"""
Test module for Fast Downward driver script. Run with

    py.test driver/tests.py
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import traceback
from types import SimpleNamespace

import pytest

from .aliases import ALIASES, PORTFOLIOS
from .arguments import EXAMPLES
from .call import check_call, _replace_paths_with_strings
from . import limits
from . import returncodes
from . import run_components
from .run_components import get_executable, REL_SEARCH_PATH
from .util import REPO_ROOT_DIR, find_domain_path

_SIGXCPU = getattr(signal, "SIGXCPU", None)
_PRESEARCH_EXITCODE_CASES = [
    (returncodes.TRANSLATE_OUT_OF_TIME, returncodes.TRANSLATE_OUT_OF_TIME),
    (-signal.SIGTERM, -signal.SIGTERM),
]
if _SIGXCPU is not None:
    _PRESEARCH_EXITCODE_CASES.append(
        (-_SIGXCPU, returncodes.TRANSLATE_OUT_OF_TIME)
    )


def cleanup():
    subprocess.check_call([sys.executable, "fast-downward.py", "--cleanup"],
                          cwd=REPO_ROOT_DIR)


def teardown_module(module):
    cleanup()


def run_driver(parameters):
    cmd = [sys.executable, "fast-downward.py", "--keep"] + parameters
    cmd = _replace_paths_with_strings(cmd)
    return subprocess.check_call(cmd, cwd=REPO_ROOT_DIR)


def test_commandline_args():
    for description, cmd in EXAMPLES:
        parameters = [x.strip('"') for x in cmd]
        run_driver(parameters)


def test_aliases():
    for alias, config in ALIASES.items():
        parameters = ["--alias", alias, "output.sas"]
        run_driver(parameters)


def test_show_aliases():
    run_driver(["--show-aliases"])


def test_portfolios():
    for name, portfolio in PORTFOLIOS.items():
        parameters = ["--portfolio", portfolio,
                      "--search-time-limit", "30m", "output.sas"]
        run_driver(parameters)


def _get_portfolio_configs(portfolio: Path):
    content = portfolio.read_bytes()
    attributes = {}
    try:
        exec(content, attributes)
    except Exception:
        traceback.print_exc()
        raise SyntaxError(
            f"The portfolio {portfolio} could not be loaded.")
    if "CONFIGS" not in attributes:
        raise ValueError("portfolios must define CONFIGS")
    return [config for _, config in attributes["CONFIGS"]]


def _convert_to_standalone_config(config):
    replacements = [
        ("H_COST_TRANSFORM", "no_transform()"),
        ("S_COST_TYPE", "normal"),
        ("BOUND", "infinity"),
    ]
    for index, part in enumerate(config):
        for before, after in replacements:
            part = part.replace(before, after)
        config[index] = part
    return config


def _run_search(config):
    check_call(
        "search",
        [get_executable("release", REL_SEARCH_PATH)] + list(config),
        stdin="output.sas")


def _get_all_portfolio_configs():
    all_configs = set()
    for portfolio in PORTFOLIOS.values():
        configs = _get_portfolio_configs(portfolio)
        all_configs |= set(tuple(_convert_to_standalone_config(config)) for config in configs)
    return all_configs


@pytest.mark.parametrize("config", _get_all_portfolio_configs())
def test_portfolio_config(config):
    _run_search(config)


@pytest.mark.skipif(not limits.can_set_time_limit(), reason="Cannot set time limits on this system")
def test_hard_time_limit():
    def preexec_fn():
        limits.set_time_limit(10)

    driver = [sys.executable, "fast-downward.py"]
    parameters = [
        "--translate", "--translate-time-limit",
        "10s", "misc/tests/benchmarks/gripper/prob01.pddl"]
    subprocess.check_call(driver + parameters, preexec_fn=preexec_fn, cwd=REPO_ROOT_DIR)

    parameters = [
        "--translate", "--translate-time-limit",
        "20s", "misc/tests/benchmarks/gripper/prob01.pddl"]
    with pytest.raises(subprocess.CalledProcessError) as exception_info:
        subprocess.check_call(driver + parameters, preexec_fn=preexec_fn, cwd=REPO_ROOT_DIR)
    assert exception_info.value.returncode == returncodes.DRIVER_INPUT_ERROR


def test_automatic_domain_file_name_computation():
    benchmarks_dir = REPO_ROOT_DIR / "benchmarks"
    for dirpath, dirnames, filenames in os.walk(benchmarks_dir):
        for filename in filenames:
            if "domain" not in filename:
                assert find_domain_path(dirpath / filename)


def _get_mock_presearch_args(tmp_path):
    return SimpleNamespace(
        build="unused",
        overall_time_limit=None,
        translate_time_limit=None,
        preprocess_time_limit=None,
        overall_memory_limit=None,
        translate_memory_limit=None,
        preprocess_memory_limit=None,
        translate_inputs=[str(tmp_path / "domain.pddl"),
                          str(tmp_path / "problem.pddl")],
        translate_options=[],
        preprocess_options=[],
        preprocess_input=tmp_path / "output.sas")


@pytest.mark.parametrize(
    "raw_exitcode, expected_exitcode",
    _PRESEARCH_EXITCODE_CASES)
@pytest.mark.parametrize("component", ["translate", "preprocess"])
def test_presearch_components_normalize_only_sigxcpu(
        monkeypatch, tmp_path, component, raw_exitcode, expected_exitcode):
    args = _get_mock_presearch_args(tmp_path)
    monkeypatch.setattr(
        run_components,
        "get_executable",
        lambda _build, _path: tmp_path / "component")

    if component == "translate":
        monkeypatch.setattr(
            run_components.call,
            "get_error_output_and_returncode",
            lambda *_args, **_kwargs: (b"", raw_exitcode))
        result = run_components.run_translate(args)
    else:
        def fail_component(_nick, cmd, **_kwargs):
            raise subprocess.CalledProcessError(raw_exitcode, cmd)

        monkeypatch.setattr(
            run_components.call, "check_call", fail_component)
        result = run_components.run_preprocess(args)

    assert result == (expected_exitcode, False)


_COMPLETE_PLAN = "(move a b)\n; cost = 7 (unit cost)\n"


def _get_direct_search_args(tmp_path):
    return SimpleNamespace(
        build="unused",
        overall_time_limit=None,
        search_time_limit=None,
        overall_memory_limit=None,
        search_memory_limit=None,
        plan_file=tmp_path / "sas_plan",
        portfolio_bound=None,
        portfolio_single_plan=False,
        portfolio=None,
        search_options=["--search", "dummy()"],
        search_input=tmp_path / "output.sas")


def _run_mock_direct_search(monkeypatch, args, raw_exitcode, create_artifacts):
    monkeypatch.setattr(
        run_components,
        "get_executable",
        lambda _build, _path: Path("downward"))

    def fake_check_call(_nick, cmd, **_kwargs):
        create_artifacts()
        if raw_exitcode:
            raise subprocess.CalledProcessError(raw_exitcode, cmd)

    monkeypatch.setattr(run_components.call, "check_call", fake_check_call)
    return run_components.run_search(args)


@pytest.mark.parametrize(
    "raw_exitcode, effective_exitcode",
    [
        (returncodes.SEARCH_OUT_OF_MEMORY,
         returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_MEMORY),
        (returncodes.SEARCH_OUT_OF_TIME,
         returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_TIME),
        (returncodes.SEARCH_OUT_OF_MEMORY_AND_TIME,
         returncodes.SEARCH_PLAN_FOUND_AND_OUT_OF_MEMORY_AND_TIME),
    ])
def test_direct_search_maps_resource_limit_with_complete_plan(
        monkeypatch, capsys, tmp_path, raw_exitcode, effective_exitcode):
    args = _get_direct_search_args(tmp_path)
    args.plan_file.write_text("old plan that must be deleted\n")

    def create_complete_plan():
        assert not args.plan_file.exists()
        args.plan_file.write_text(_COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch, args, raw_exitcode, create_complete_plan)

    assert result == (effective_exitcode, True)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {raw_exitcode}",
        "search resource-limit exit with complete plan: "
        f"raw_exit_code={raw_exitcode} "
        f"effective_exit_code={effective_exitcode}",
    ]


@pytest.mark.parametrize(
    "artifact_kind", ["none", "truncated", "symlink", "directory", "multiple"])
def test_direct_search_rejects_uncertified_plan(
        monkeypatch, capsys, tmp_path, artifact_kind):
    args = _get_direct_search_args(tmp_path)

    def create_artifacts():
        if artifact_kind == "truncated":
            args.plan_file.write_text("(move a b)\n")
        elif artifact_kind == "symlink":
            target = tmp_path / "complete-plan-target"
            target.write_text(_COMPLETE_PLAN)
            args.plan_file.symlink_to(target)
        elif artifact_kind == "directory":
            args.plan_file.mkdir()
        elif artifact_kind == "multiple":
            args.plan_file.write_text(_COMPLETE_PLAN)
            Path(f"{args.plan_file}.2").write_text(_COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch, args, returncodes.SEARCH_OUT_OF_TIME, create_artifacts)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_ignores_plan_artifact_from_before_search(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    stale_plan = Path(f"{args.plan_file}.2")
    stale_plan.write_text(_COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch, args, returncodes.SEARCH_OUT_OF_TIME, lambda: None)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert stale_plan.exists()
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_rejects_modified_preexisting_plan_artifact(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    preexisting_plan = Path(f"{args.plan_file}.2")
    preexisting_plan.write_text("stale\n")

    def create_artifacts():
        args.plan_file.write_text(_COMPLETE_PLAN)
        preexisting_plan.write_text(_COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch, args, returncodes.SEARCH_OUT_OF_TIME, create_artifacts)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_rejects_duplicate_cost_footer(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)

    def create_plan_with_duplicate_footer():
        args.plan_file.write_text(
            "; cost = 6 (unit cost)\n" + _COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch,
        args,
        returncodes.SEARCH_OUT_OF_TIME,
        create_plan_with_duplicate_footer)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_rejects_hardlinked_plan(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    target = tmp_path / "complete-plan-target"

    def create_hardlinked_plan():
        target.write_text(_COMPLETE_PLAN)
        os.link(target, args.plan_file)

    result = _run_mock_direct_search(
        monkeypatch,
        args,
        returncodes.SEARCH_OUT_OF_TIME,
        create_hardlinked_plan)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert args.plan_file.stat().st_nlink == 2
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_rejects_plan_replaced_after_snapshot(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    real_snapshot = run_components.PlanManager.get_plan_artifact_snapshot
    snapshot_calls = 0

    def snapshot_then_replace_plan(plan_manager):
        nonlocal snapshot_calls
        snapshot_calls += 1
        snapshot = real_snapshot(plan_manager)
        if snapshot_calls == 2:
            replacement = tmp_path / "replacement-plan"
            replacement.write_text(
                "(different action)\n; cost = 99 (unit cost)\n")
            replacement.replace(args.plan_file)
        return snapshot

    monkeypatch.setattr(
        run_components.PlanManager,
        "get_plan_artifact_snapshot",
        snapshot_then_replace_plan)
    result = _run_mock_direct_search(
        monkeypatch,
        args,
        returncodes.SEARCH_OUT_OF_TIME,
        lambda: args.plan_file.write_text(_COMPLETE_PLAN))

    assert snapshot_calls == 2
    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_does_not_reuse_deleted_canonical_plan(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    args.plan_file.write_text(_COMPLETE_PLAN)

    result = _run_mock_direct_search(
        monkeypatch, args, returncodes.SEARCH_OUT_OF_TIME, lambda: None)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert not args.plan_file.exists()
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


def test_direct_search_rejects_plan_when_inventory_is_unavailable(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)

    def fail_inventory(_self):
        raise PermissionError("test inventory failure")

    monkeypatch.setattr(
        run_components.PlanManager,
        "get_plan_artifact_snapshot",
        fail_inventory)
    result = _run_mock_direct_search(
        monkeypatch,
        args,
        returncodes.SEARCH_OUT_OF_TIME,
        lambda: args.plan_file.write_text(_COMPLETE_PLAN))

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {returncodes.SEARCH_OUT_OF_TIME}",
    ]


@pytest.mark.parametrize(
    "raw_exitcode",
    [
        returncodes.SEARCH_UNSOLVABLE,
        returncodes.SEARCH_UNSOLVED_INCOMPLETE,
        returncodes.SEARCH_UNSUPPORTED,
        -9,
    ])
def test_direct_search_preserves_other_exitcodes(
        monkeypatch, capsys, tmp_path, raw_exitcode):
    args = _get_direct_search_args(tmp_path)
    result = _run_mock_direct_search(
        monkeypatch,
        args,
        raw_exitcode,
        lambda: args.plan_file.write_text(_COMPLETE_PLAN))

    assert result == (raw_exitcode, False)
    assert capsys.readouterr().out.splitlines() == [
        f"search raw exit code: {raw_exitcode}",
    ]


def test_direct_search_preserves_unexpected_low_exitcode_assertion(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    with pytest.raises(AssertionError, match="got returncode < 10: 1"):
        _run_mock_direct_search(monkeypatch, args, 1, lambda: None)

    assert capsys.readouterr().out.splitlines() == ["search raw exit code: 1"]


def test_direct_search_logs_success_raw_exitcode(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    result = _run_mock_direct_search(monkeypatch, args, 0, lambda: None)

    assert result == (returncodes.SUCCESS, True)
    assert capsys.readouterr().out.splitlines() == ["search raw exit code: 0"]


def test_portfolio_search_does_not_log_direct_raw_exitcode(
        monkeypatch, capsys, tmp_path):
    args = _get_direct_search_args(tmp_path)
    args.portfolio = tmp_path / "portfolio.py"
    args.search_options = []
    monkeypatch.setattr(
        run_components,
        "get_executable",
        lambda _build, _path: Path("downward"))
    monkeypatch.setattr(
        run_components.portfolio_runner,
        "run",
        lambda *_args: (returncodes.SEARCH_OUT_OF_TIME, False))

    result = run_components.run_search(args)

    assert result == (returncodes.SEARCH_OUT_OF_TIME, False)
    assert capsys.readouterr().out == ""
