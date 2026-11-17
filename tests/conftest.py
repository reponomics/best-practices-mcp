"""Keep test subprocesses independent of a calling Git hook's repository."""

import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_git_environment():
    # Git's documented list includes worktree, index, object and config overrides.
    # https://git-scm.com/docs/githooks#_description
    variables = subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], text=True, timeout=10
    ).splitlines()
    with pytest.MonkeyPatch.context() as environment:
        for name in variables:
            environment.delenv(name, raising=False)
        yield
