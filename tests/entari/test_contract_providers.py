from __future__ import annotations

from pathlib import Path
import subprocess
import sys

_SCENARIO = Path(__file__).with_name("_contract_providers_scenarios.py")


def test_contract_provider_waiter_scenarios_are_isolated() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and test script
        [sys.executable, str(_SCENARIO)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
