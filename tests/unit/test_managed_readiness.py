"""The managed edge is honest: placeholders prevent a serving process from starting."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from claims_integrity_investigator.managed_readiness import (
    INCOMPLETE_MANAGED_OPERATIONS,
    assert_managed_profile_ready,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The managed adapter family. ``onprem`` raises too, deliberately and permanently (it is the
#: portability placeholder), so it is out of scope here: this list gates a MANAGED boot.
MANAGED_ADAPTERS = REPO_ROOT / "src" / "claims_integrity_investigator" / "adapters" / "gcp"


def _raises_not_implemented(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when this method body can raise ``NotImplementedError``, at any depth."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Raise):
            continue
        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True
    return False


def _managed_operations_that_raise() -> set[str]:
    """Every managed operation that is still a placeholder, read from the source.

    Static rather than dynamic on purpose. A placeholder raise sits BEHIND a lazy SDK import
    and a configuration refusal, so reaching it by calling the method needs an SDK and
    credentials the offline gate must not have; and a method no test happens to call would be
    invisible to a dynamic sweep, which is exactly the omission this test exists to catch.

    The identifier is the one ``INCOMPLETE_MANAGED_OPERATIONS`` uses, ``module.Class.method``,
    because ``_incomplete_operations_for_bindings`` splits it back into the binding target.
    """
    operations: set[str] = set()
    for path in sorted(MANAGED_ADAPTERS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if _raises_not_implemented(item):
                    operations.add(f"{path.stem}.{node.name}.{item.name}")
    return operations


def test_offline_and_exit_profiles_remain_available() -> None:
    assert_managed_profile_ready("local")
    assert_managed_profile_ready("onprem")


def test_managed_profile_refuses_while_operations_are_placeholders() -> None:
    assert INCOMPLETE_MANAGED_OPERATIONS
    with pytest.raises(RuntimeError, match="not production ready"):
        assert_managed_profile_ready("gcp")


def test_the_declared_list_covers_every_managed_operation_that_raises() -> None:
    """The list is checked against the adapters, not against somebody's memory of them.

    An operation that raises but is not declared is harmless only while some OTHER entry still
    refuses the boot. The day the last of those lands, the preflight goes green and that path
    fails at request time instead, on a service the preflight just called production ready. So
    the two sets are held equal, in both directions: an entry that no longer raises is the
    opposite failure, a managed boot refused for work that is already done.
    """
    raising = _managed_operations_that_raise()
    declared = set(INCOMPLETE_MANAGED_OPERATIONS)

    assert raising, "guard the guard: the scan found no placeholder at all, so it proves nothing"
    assert not raising - declared, (
        "a managed operation raises NotImplementedError but is not declared incomplete, so the "
        "preflight would pass and the call would fail at request time instead: "
        f"{sorted(raising - declared)}"
    )
    assert not declared - raising, (
        "an operation is declared incomplete but no longer raises, so the preflight refuses a "
        f"managed boot for work that has already landed: {sorted(declared - raising)}"
    )
