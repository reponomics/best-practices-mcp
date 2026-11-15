"""Published artifacts must remain data in the read-only consumer check."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/verify-release.yml").read_text())
JOB = WORKFLOW["jobs"]["verify"]


def test_verification_cannot_publish_or_mint_identity_tokens():
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert JOB["permissions"] == {"contents": "read", "actions": "read"}
    assert "environment" not in JOB
    assert "secrets." not in str(WORKFLOW)
    token_steps = [step for step in JOB["steps"] if "GH_TOKEN" in step.get("env", {})]
    assert [step["name"] for step in token_steps] == ["Verify downloaded public release"]


def test_automatic_and_manual_events_only_run_trusted_verifier():
    triggers = WORKFLOW[True]  # PyYAML's YAML 1.1 parser treats `on` as true.
    assert triggers["workflow_run"] == {
        "workflows": ["Publish to PyPI"],
        "types": ["completed"],
    }
    assert "release" not in triggers
    guard = JOB["if"]
    for boundary in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'workflow_dispatch'",
        "github.event.workflow_run.path == '.github/workflows/release.yml'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
        "github.ref == 'refs/heads/main'",
    ):
        assert boundary in guard
    checkout = next(step for step in JOB["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    assert "head_sha" not in str(checkout)
    assert JOB["env"]["EXPECTED_SHA"] == "${{ github.event.workflow_run.head_sha }}"


def test_setup_and_retention_do_not_execute_published_packages():
    install = next(
        step for step in JOB["steps"] if step["name"] == "Install only locked verification tools"
    )
    assert "--locked --only-group verification-tools --no-install-project" in install["run"]
    verifier = next(
        step for step in JOB["steps"] if step["name"] == "Verify downloaded public release"
    )
    assert "--expected-sha" in verifier["run"]
    assert "${{" not in verifier["run"]
    upload = JOB["steps"][-1]
    assert upload["if"] == "always()"
    assert upload["with"]["retention-days"] == 30
    assert upload["with"]["if-no-files-found"] == "error"
