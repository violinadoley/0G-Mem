"""Shared pytest fixtures. All use mock clients — no network or keys required."""

import pytest


@pytest.fixture
def mock_storage():
    from tests.test_memory import MockStorage
    return MockStorage()


@pytest.fixture
def mock_da():
    from tests.test_memory import MockDA
    return MockDA()


@pytest.fixture
def mock_chain():
    from tests.test_memory import MockChain
    return MockChain()


@pytest.fixture
def mock_compute():
    from tests.test_memory import MockCompute
    return MockCompute()


@pytest.fixture
def memory(mock_storage, mock_da, mock_chain, mock_compute):
    from ogmem.memory import VerifiableMemory
    return VerifiableMemory(
        agent_id="test-agent",
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        _storage=mock_storage,
        _da=mock_da,
        _chain=mock_chain,
        _compute=mock_compute,
    )
