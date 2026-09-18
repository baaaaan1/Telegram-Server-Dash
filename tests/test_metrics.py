"""Tests for metrics collection and server probes."""

import pytest

from core.probe import connectivity_test, latency_test
from core.ssh import CommandResult


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_dataclass_fields(self):
        """Test CommandResult has expected fields."""
        result = CommandResult(stdout="out", stderr="", exit_code=0, duration=0.5)
        assert result.stdout == "out"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.duration == 0.5


class TestConnectivityTest:
    """Tests for connectivity_test function."""

    @pytest.mark.asyncio
    async def test_successful_connectivity(self):
        """Test connectivity test on successful command."""

        class MockResult:
            def __init__(self):
                self.exit_code = 0

        class MockConn:
            async def run(self, cmd):
                return MockResult()

        result = await connectivity_test(MockConn())
        assert result is True

    @pytest.mark.asyncio
    async def test_failed_connectivity(self):
        """Test connectivity test on failed command."""

        class MockResult:
            def __init__(self):
                self.exit_code = 1

        class MockConn:
            async def run(self, cmd):
                return MockResult()

        result = await connectivity_test(MockConn())
        assert result is False


class TestLatencyTest:
    """Tests for latency_test function."""

    @pytest.mark.asyncio
    async def test_latency_parses_ping_output(self):
        """Test latency parses ping output correctly."""

        class MockResult:
            def __init__(self):
                self.exit_code = 0
                self.stdout = "PING 127.0.0.1: 1 time\ntime=0.5ms"

        class MockConn:
            async def run(self, cmd):
                return MockResult()

        latency = await latency_test(MockConn())
        assert latency >= 0

    @pytest.mark.asyncio
    async def test_latency_on_failure(self):
        """Test latency returns -1 on failure."""

        class MockResult:
            def __init__(self):
                self.exit_code = 1
                self.stdout = ""
                self.stderr = "Network unreachable"

        class MockConn:
            async def run(self, cmd):
                return MockResult()

        latency = await latency_test(MockConn())
        assert latency == -1
