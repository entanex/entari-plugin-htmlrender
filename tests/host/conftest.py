from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Launart is asyncio-native; keep host lifecycle tests on that backend."""
    return "asyncio"
