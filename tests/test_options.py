import pathlib

import pytest

import langgraph_codex


def test_workflow_policy_allows_configured_request_options(tmp_path: pathlib.Path) -> None:
    policy = langgraph_codex.codex_workflow_policy(
        "remediation",
        writable_roots=[tmp_path / "service"],
        profiles=["ci"],
        sandbox_modes=[langgraph_codex.CodexSandbox.WORKSPACE_WRITE],
        models=["gpt-5.1"],
    )
    options = {
        langgraph_codex.ExecutionOption.ADDITIONAL_WRITABLE_ROOTS.value: [
            tmp_path / "service" / "src"
        ],
        langgraph_codex.ExecutionOption.PROFILE.value: "ci",
        langgraph_codex.ExecutionOption.SANDBOX.value: langgraph_codex.CodexSandbox.WORKSPACE_WRITE,
        langgraph_codex.ExecutionOption.MODEL.value: "gpt-5.1",
    }

    restricted_options = policy.restrict(options, workspace_path=tmp_path)

    assert restricted_options == options
    assert restricted_options is not options


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        (langgraph_codex.ExecutionOption.PROFILE, "local", "profile='local'"),
        (langgraph_codex.ExecutionOption.SANDBOX, "danger-full-access", "sandbox="),
        (langgraph_codex.ExecutionOption.MODEL, "gpt-6", "model='gpt-6'"),
    ],
)
def test_workflow_policy_rejects_disallowed_choices(
    option: langgraph_codex.ExecutionOption,
    value: object,
    message: str,
) -> None:
    policy = langgraph_codex.codex_workflow_policy(
        "audit",
        profiles=["ci"],
        sandbox_modes=[langgraph_codex.CodexSandbox.READ_ONLY],
        models=["gpt-5.1"],
    )

    with pytest.raises(langgraph_codex.WorkflowPolicyViolation, match=message):
        policy.validate({option.value: value})


def test_workflow_policy_rejects_writable_roots_outside_allowed_root(
    tmp_path: pathlib.Path,
) -> None:
    policy = langgraph_codex.codex_workflow_policy(
        "docs",
        writable_roots=["allowed"],
    )

    with pytest.raises(langgraph_codex.WorkflowPolicyViolation, match="writable root"):
        policy.validate(
            {
                langgraph_codex.ExecutionOption.ADDITIONAL_WRITABLE_ROOTS.value: [
                    tmp_path / "outside"
                ]
            },
            workspace_path=tmp_path,
        )


def test_restrict_options_by_workflow_selects_named_policy(tmp_path: pathlib.Path) -> None:
    policy = langgraph_codex.codex_workflow_policy(
        "audit",
        writable_roots=[],
        sandbox_modes=[langgraph_codex.CodexSandbox.READ_ONLY],
    )

    restricted_options = langgraph_codex.restrict_options_by_workflow(
        "audit",
        {langgraph_codex.ExecutionOption.SANDBOX.value: langgraph_codex.CodexSandbox.READ_ONLY},
        {"audit": policy},
        workspace_path=tmp_path,
    )

    assert restricted_options == {langgraph_codex.ExecutionOption.SANDBOX.value: "read-only"}


def test_restrict_options_by_workflow_rejects_unknown_workflow() -> None:
    with pytest.raises(langgraph_codex.WorkflowPolicyViolation, match="No Codex workflow policy"):
        langgraph_codex.restrict_options_by_workflow("missing", {}, {})
