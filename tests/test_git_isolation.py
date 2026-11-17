"""Hook-inherited Git settings must not redirect temporary-repository tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git_state(directory):
    return {
        path.relative_to(directory): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "all_settings", [False, True], ids=["worktree-hook", "repository-settings"]
)
def test_nested_pytest_leaves_inherited_repository_untouched(tmp_path, all_settings):
    outer = tmp_path / "outer"
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", "init", "--initial-branch=sentinel", str(outer)], env=env, check=True)
    (outer / "sentinel.txt").write_text("Leave this repository alone.\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=outer, env=env, check=True)
    git_dir = outer / ".git"
    before = git_state(git_dir)
    env["GIT_DIR"] = str(git_dir)
    if all_settings:
        env.update(
            GIT_WORK_TREE=str(outer),
            GIT_COMMON_DIR=str(git_dir),
            GIT_INDEX_FILE=str(git_dir / "index"),
            GIT_OBJECT_DIRECTORY=str(git_dir / "objects"),
            GIT_CONFIG=str(git_dir / "config"),
            GIT_CONFIG_PARAMETERS="'core.bare=true'",
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="user.name",
            GIT_CONFIG_VALUE_0="Hook identity",
        )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_release_check.py::test_release_git_identity_must_match_event_tag_and_main_ancestry",
            "tests/test_verification_support.py::test_git_uses_requested_repository_and_strips_output",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert git_state(git_dir) == before, "Nested tests modified the inherited Git repository"
    assert (outer / "sentinel.txt").read_text(encoding="utf-8") == "Leave this repository alone.\n"
    assert result.returncode == 0, result.stdout + result.stderr
