"""Server connectivity probes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.ssh import CommandResult


@dataclass(frozen=True, slots=True)
class ServerMetrics:
    """Snapshot of read-only server health metrics."""

    online: bool
    hostname: str = "unknown"
    uptime: str = "unknown"
    load: str = "unknown"
    memory: str = "unknown"
    disk: str = "unknown"
    latency_ms: float = -1


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


async def check_hostname(connection) -> str:
    """Get the server hostname."""
    result = await connection.run("hostname 2>/dev/null || echo unknown")
    return result.stdout.strip() if result.exit_code == 0 else "unknown"


async def check_memory(connection) -> str:
    """Get used and total memory in MiB."""
    result = await connection.run(
        "free -m | awk 'NR==2 {printf \"%s/%s MiB (%.0f%%)\", $3, $2, ($3/$2)*100}'"
    )
    return result.stdout.strip() if result.exit_code == 0 and result.stdout.strip() else "unknown"


async def check_disk(connection) -> str:
    """Get root filesystem usage."""
    result = await connection.run("df -hP / | awk 'NR==2 {printf \"%s/%s (%s)\", $3, $2, $5}'")
    return result.stdout.strip() if result.exit_code == 0 and result.stdout.strip() else "unknown"


async def collect_server_metrics(connection) -> ServerMetrics:
    """Collect a single server status snapshot."""
    if not await connectivity_test(connection):
        return ServerMetrics(online=False)

    latency, uptime_result, load, hostname, memory, disk = await asyncio.gather(
        latency_test(connection),
        check_uptime(connection),
        check_load_avg(connection),
        check_hostname(connection),
        check_memory(connection),
        check_disk(connection),
    )
    uptime = (
        uptime_result.stdout.strip()
        if uptime_result.exit_code == 0 and uptime_result.stdout.strip()
        else "unknown"
    )
    return ServerMetrics(
        online=True,
        hostname=hostname,
        uptime=uptime,
        load=load,
        memory=memory,
        disk=disk,
        latency_ms=latency,
    )


# ── Detailed monitoring probes (htop-like) ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class CpuDetails:
    """Detailed CPU information."""

    model: str
    cores: int
    usage_per_core: list[float]
    overall_usage: float
    top_processes: list[dict]
    temperature: str = "N/A"


@dataclass(frozen=True, slots=True)
class MemoryDetails:
    """Detailed memory information."""

    total_mb: int
    used_mb: int
    free_mb: int
    available_mb: int
    cached_mb: int
    buffers_mb: int
    swap_total_mb: int
    swap_used_mb: int
    swap_free_mb: int
    top_processes: list[dict]


@dataclass(frozen=True, slots=True)
class NetworkDetails:
    """Detailed network information."""

    interfaces: list[dict]
    total_rx_bytes: int
    total_tx_bytes: int
    active_connections: int
    established_connections: int
    listening_ports: list[dict]


@dataclass(frozen=True, slots=True)
class DiskDetails:
    """Detailed disk information."""

    partitions: list[dict]
    total_inodes: int
    used_inodes: int
    io_stats: list[dict]


async def check_cpu_model(connection) -> str:
    """Get CPU model name."""
    result = await connection.run(
        "lscpu | grep 'Model name' | sed 's/Model name:\\s*//' 2>/dev/null || echo 'Unknown'"
    )
    return result.stdout.strip() if result.exit_code == 0 else "Unknown"


async def check_cpu_cores(connection) -> int:
    """Get number of CPU cores."""
    result = await connection.run("nproc 2>/dev/null || echo 1")
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 1


async def check_cpu_usage_per_core(connection) -> list[float]:
    """Get CPU usage percentage per core using /proc/stat sampling."""
    cmd = r"""
cat /proc/stat | grep '^cpu' | tail -n +2 | while read -r line; do
    vals=($line)
    idle=${vals[4]}
    total=0
    for v in "${vals[@]:1}"; do total=$((total + v)); done
    echo "$idle $total"
done
"""
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    cores_data = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            cores_data.append((int(parts[0]), int(parts[1])))

    if not cores_data:
        return []

    await asyncio.sleep(0.5)

    result2 = await connection.run(cmd)
    if result2.exit_code != 0:
        return []

    cores_data2 = []
    for line in result2.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            cores_data2.append((int(parts[0]), int(parts[1])))

    usages = []
    for (idle1, total1), (idle2, total2) in zip(cores_data, cores_data2, strict=False):
        total_diff = total2 - total1
        idle_diff = idle2 - idle1
        if total_diff > 0:
            usage = round((1 - idle_diff / total_diff) * 100, 1)
            usages.append(max(0.0, min(100.0, usage)))
        else:
            usages.append(0.0)

    return usages


async def check_cpu_temperature(connection) -> str:
    """Get CPU temperature if available."""
    result = await connection.run("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0")
    if result.exit_code == 0:
        try:
            temp = int(result.stdout.strip())
            if temp > 0:
                return f"{temp / 1000:.1f}°C"
        except ValueError:
            pass
    return "N/A"


async def check_top_processes_cpu(connection, limit: int = 5) -> list[dict]:
    """Get top processes by CPU usage."""
    cmd = f"ps aux --sort=-%cpu | head -n {limit + 1} | tail -n {limit}"
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    processes = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append(
                {
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10][:50],
                }
            )
    return processes


async def check_top_processes_mem(connection, limit: int = 5) -> list[dict]:
    """Get top processes by memory usage."""
    cmd = f"ps aux --sort=-%mem | head -n {limit + 1} | tail -n {limit}"
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    processes = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append(
                {
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10][:50],
                }
            )
    return processes


async def collect_cpu_details(connection) -> CpuDetails:
    """Collect detailed CPU information."""
    model, cores, usage_per_core, temp, top_procs = await asyncio.gather(
        check_cpu_model(connection),
        check_cpu_cores(connection),
        check_cpu_usage_per_core(connection),
        check_cpu_temperature(connection),
        check_top_processes_cpu(connection),
    )

    overall = round(sum(usage_per_core) / len(usage_per_core), 1) if usage_per_core else 0.0

    return CpuDetails(
        model=model,
        cores=cores,
        usage_per_core=usage_per_core,
        overall_usage=overall,
        top_processes=top_procs,
        temperature=temp,
    )


async def collect_memory_details(connection) -> MemoryDetails:
    """Collect detailed memory information."""
    cmd = r"""
free -m | awk '
NR==2 {printf "%d %d %d %d %d %d\n", $2, $3, $4, $7, $6, $7}
NR==3 {printf "%d %d %d\n", $2, $3, $4}
'
"""
    result = await connection.run(cmd)
    mem_total = mem_used = mem_free = mem_avail = mem_cached = mem_buf = 0
    swap_total = swap_used = swap_free = 0

    if result.exit_code == 0:
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 1:
            parts = lines[0].split()
            if len(parts) >= 6:
                mem_total, mem_used, mem_free, mem_avail, mem_cached, mem_buf = (
                    int(parts[0]),
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                    int(parts[5]),
                )
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                swap_total, swap_used, swap_free = int(parts[0]), int(parts[1]), int(parts[2])

    top_procs = await check_top_processes_mem(connection)

    return MemoryDetails(
        total_mb=mem_total,
        used_mb=mem_used,
        free_mb=mem_free,
        available_mb=mem_avail,
        cached_mb=mem_cached,
        buffers_mb=mem_buf,
        swap_total_mb=swap_total,
        swap_used_mb=swap_used,
        swap_free_mb=swap_free,
        top_processes=top_procs,
    )


async def check_network_interfaces(connection) -> list[dict]:
    """Get network interface statistics."""
    cmd = r"""
cat /proc/net/dev | tail -n +3 | while read -r line; do
    iface=$(echo "$line" | awk -F: '{print $1}' | tr -d ' ')
    rx=$(echo "$line" | awk -F: '{print $2}' | awk '{print $1}')
    tx=$(echo "$line" | awk -F: '{print $2}' | awk '{print $9}')
    echo "$iface $rx $tx"
done
"""
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    interfaces = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            interfaces.append(
                {
                    "name": parts[0],
                    "rx_bytes": int(parts[1]),
                    "tx_bytes": int(parts[2]),
                }
            )
    return interfaces


async def check_active_connections(connection) -> tuple[int, int]:
    """Get active and established connections count."""
    result = await connection.run("ss -tun state established | wc -l")
    established = int(result.stdout.strip()) - 1 if result.exit_code == 0 else 0

    result2 = await connection.run("ss -tun | wc -l")
    total = int(result2.stdout.strip()) - 1 if result2.exit_code == 0 else 0

    return max(0, total), max(0, established)


async def check_listening_ports(connection) -> list[dict]:
    """Get listening ports and services."""
    cmd = "ss -tlnp 2>/dev/null | tail -n +2"
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    ports = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 4:
            local = parts[3]
            port = local.rsplit(":", 1)[-1] if ":" in local else local
            process = ""
            if "users:" in line:
                process = line.split('users:("')[1].split('"')[0] if '"(' in line else ""
            ports.append({"port": port, "process": process})
    return ports


async def collect_network_details(connection) -> NetworkDetails:
    """Collect detailed network information."""
    interfaces, (total, established), ports = await asyncio.gather(
        check_network_interfaces(connection),
        check_active_connections(connection),
        check_listening_ports(connection),
    )

    total_rx = sum(i["rx_bytes"] for i in interfaces)
    total_tx = sum(i["tx_bytes"] for i in interfaces)

    return NetworkDetails(
        interfaces=interfaces,
        total_rx_bytes=total_rx,
        total_tx_bytes=total_tx,
        active_connections=total,
        established_connections=established,
        listening_ports=ports,
    )


async def check_disk_partitions(connection) -> list[dict]:
    """Get disk partition usage."""
    cmd = "df -hP | tail -n +2 | grep -v tmpfs"
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    partitions = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 6:
            partitions.append(
                {
                    "device": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "use_percent": parts[4],
                    "mount": parts[5],
                }
            )
    return partitions


async def check_inodes(connection) -> tuple[int, int]:
    """Get inode usage for root filesystem."""
    cmd = "df -iP / | tail -1 | awk '{print $2, $3}'"
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return 0, 0

    parts = result.stdout.strip().split()
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 0, 0


async def check_io_stats(connection) -> list[dict]:
    """Get disk I/O statistics."""
    cmd = r"""
cat /proc/diskstats | awk '{
    if ($3 ~ /^(sd|vd|nvme)/ && $3 !~ /[0-9]$/) {
        printf "%s %s %s %s %s\n", $3, $6, $7, $10, $11
    }
}'
"""
    result = await connection.run(cmd)
    if result.exit_code != 0:
        return []

    stats = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 5:
            stats.append(
                {
                    "device": parts[0],
                    "reads": int(parts[1]),
                    "writes": int(parts[2]),
                    "read_ms": int(parts[3]),
                    "write_ms": int(parts[4]),
                }
            )
    return stats


async def collect_disk_details(connection) -> DiskDetails:
    """Collect detailed disk information."""
    partitions, (total_inodes, used_inodes), io_stats = await asyncio.gather(
        check_disk_partitions(connection),
        check_inodes(connection),
        check_io_stats(connection),
    )

    return DiskDetails(
        partitions=partitions,
        total_inodes=total_inodes,
        used_inodes=used_inodes,
        io_stats=io_stats,
    )
