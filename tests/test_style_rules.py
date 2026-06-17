import pathlib


def test_package_does_not_use_qualified_typing_any() -> None:
    package_root = pathlib.Path(__file__).parents[1] / "langgraph_codex"
    forbidden_pattern = "typing" + ".Any"
    offenders = [
        str(path.relative_to(package_root.parent))
        for path in sorted(package_root.rglob("*.py"))
        if forbidden_pattern in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
