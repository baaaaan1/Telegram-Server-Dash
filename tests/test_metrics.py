"""Tests for metrics collection and server probes."""

import pytest

from core.probe import collect_server_metrics, connectivity_test, latency_test
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


class TestServerMetrics:
    """Tests for complete server metric snapshots."""

    @pytest.mark.asyncio
    async def test_collects_native_metrics(self):
        """Collect the host fields shown by the status handler."""

        class MockConn:
            async def run(self, command):
                outputs = {
                    "echo ok": "ok\n",
                    "uptime": "up 2 days\n",
                    "loadavg": "0.10 0.20 0.30\n",
                    "hostname": "vps-01\n",
                    "free -m": "128/1024 MiB (13%)",
                    "df -hP": "4G/20G (20%)",
                    "ping -c": "time=0.25 ms\n",
                }
                stdout = next(
                    (output for marker, output in outputs.items() if marker in command), ""
                )
                return CommandResult(stdout=stdout, stderr="", exit_code=0, duration=0.01)

        metrics = await collect_server_metrics(MockConn())

        assert metrics.online is True
        assert metrics.hostname == "vps-01"
        assert metrics.uptime == "up 2 days"
        assert metrics.load == "0.10 0.20 0.30"
        assert metrics.memory == "128/1024 MiB (13%)"
        assert metrics.disk == "4G/20G (20%)"
        assert metrics.latency_ms == 0.25

    @pytest.mark.asyncio
    async def test_offline_server_stops_after_connectivity_check(self):
        """Offline servers return a safe empty snapshot."""

        class MockConn:
            async def run(self, command):
                return CommandResult(stdout="", stderr="failed", exit_code=1, duration=0.01)

        metrics = await collect_server_metrics(MockConn())

        assert metrics.online is False
        assert metrics.hostname == "unknown"
