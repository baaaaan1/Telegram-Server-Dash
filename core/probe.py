"""Server connectivity probes."""

from __future__ import annotations

from core.ssh import CommandResult


async def connectivity_test(connection, command: str = "echo ok") -> bool:
    """Simple connectivity test to server."""
    result = await connection.run(command)
    return result.exit_code == 0


async def latency_test(connection, host: str | None = None) -> float:
    """Measure latency to server using ping (local only)."""
    result = await connection.run("ping -c 1 -W 1 127.0.0.1 2>/dev/null || echo 1")
    if result.exit_code != 0:
        return -1

    import re

    match = re.search(r"time=(\d+\.?\d*)", result.stdout)
    if match:
        return float(match.group(1))

    return -1


async def check_uptime(connection) -> CommandResult:
    """Get system uptime from server."""
    return await connection.run(
        "uptime -p 2>/dev/null || cat /proc/uptime | awk '{print $1\" seconds\"}' || echo 'unknown'"
    )


async def check_load_avg(connection) -> str:
    """Get load average."""
    result = await connection.run('cat /proc/loadavg | awk \'{print $1" " $2" " $3}\'')
    if result.exit_code == 0:
        return result.stdout.strip()
    return "unknown"
