"""Monitoring handlers - detailed system dashboards (htop-like).

Every screen follows the same hybrid contract: one navigation header with the
Reply Keyboard plus one rich report message whose inline panel can refresh,
switch between compact and detail density, reveal sensitive rows, and paginate
hosts. Panel actions re-render that same message with ``edit_text``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.formatting import (
    Entity,
    blockquote,
    entity,
    esc,
    expandable_blockquote,
    italic,
    metric,
    progress_bar,
    to_plain_text,
)
from bot.keyboards import make_home_keyboard, make_monitor_keyboard
from bot.nav import push_screen
from bot.render import ScreenReport, paginate, send_report
from bot.services import Services, log_user_action
from bot.texts import Messages
from config import load_server_registry, load_settings
from config.servers import ServerConfig
from core.probe import (
    collect_cpu_details,
    collect_disk_details,
    collect_memory_details,
    collect_network_details,
)
from core.ssh import LocalConnection, SSHConnection, create_ssh_pool

router = Router()
logger = logging.getLogger(__name__)

Connection = SSHConnection | LocalConnection
BlockBuilder = Callable[[Connection, ServerConfig, bool, bool], Awaitable[list[str]]]

TOP_PROCESS_LIMIT = 5
LISTENING_PORT_LIMIT = 10

SCREEN_METHODS = {
    "cpu": Messages.METHOD_CPU_LINE,
    "memory": Messages.METHOD_MEMORY_LINE,
    "network": Messages.METHOD_NETWORK_LINE,
    "disk": Messages.METHOD_DISK_LINE,
    "processes": Messages.METHOD_PROCESSES_LINE,
}


def _format_bytes(size: int) -> str:
    """Format bytes to a human readable string."""
    value = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def _enabled_servers() -> dict[str, ServerConfig]:
    """Load every enabled server from the registry (no message side effects)."""
    _settings, config_path = load_settings()
    return load_server_registry(config_path).get_enabled_servers()


async def _load_enabled_servers(message: Message) -> dict[str, ServerConfig] | None:
    """Load enabled servers, answering with the home keyboard when the list is empty."""
    enabled = _enabled_servers()
    if not enabled:
        await message.answer(Messages.REPORT_NO_SERVERS, reply_markup=make_home_keyboard())
        return None
    return enabled


async def _collect_blocks(
    servers: dict[str, ServerConfig],
    screen: str,
    build: BlockBuilder,
    *,
    detail: bool,
    reveal: bool,
) -> tuple[list[Entity], bool]:
    """Run one block builder per server, degrading to an offline block on failure."""
    pool = create_ssh_pool(servers)
    blocks: list[Entity] = []
    attention = False
    try:
        for name, server in servers.items():
            try:
                blocks.append(entity(*await build(pool[name], server, detail, reveal)))
            except Exception:
                logger.exception("Failed to collect %s details for server %s", screen, name)
                attention = True
                head = Messages.server_line(name, online=False, group=server.group)
                blocks.append(entity(head, f"└ {Messages.REPORT_UNREACHABLE}"))
    finally:
        await asyncio.gather(
            *(connection.close() for connection in pool.values()), return_exceptions=True
        )
    return blocks, attention


async def render_screen_report(  # noqa: PLR0913 - one renderer serves every monitor screen
    screen: str,
    *,
    servers: dict[str, ServerConfig] | None = None,
    detail: bool = False,
    reveal: bool = False,
    page: int = 1,
) -> ScreenReport:
    """Render a monitor dashboard for one page of the registry."""
    available = _enabled_servers() if servers is None else servers
    if not available:
        return ScreenReport(screen=screen, text=Messages.REPORT_NO_SERVERS)

    names, current, pages = paginate(list(available), page)
    subset = {name: available[name] for name in names}
    blocks, attention = await _collect_blocks(
        subset,
        screen,
        SCREEN_BUILDERS[screen],
        detail=detail,
        reveal=reveal,
    )

    lines = [Messages.report_heading(screen, SCREEN_METHODS.get(screen, ""))]
    if pages > 1:
        lines.append(Messages.REPORT_PAGE.format(page=current, pages=pages, total=len(available)))
    lines.extend(expandable_blockquote(block) if detail else blockquote(block) for block in blocks)

    text = "\n\n".join(lines)
    return ScreenReport(
        screen=screen,
        text=text,
        page=current,
        pages=pages,
        detail=detail,
        reveal=reveal,
        attention=attention,
        copy_text=to_plain_text(text),
    )


async def _cpu_block(
    connection: Connection,
    server: ServerConfig,
    detail: bool,
    reveal: bool,
) -> list[str]:
    """CPU rows; per-core bars and top processes only in detail mode."""
    cpu = await collect_cpu_details(connection)
    lines = [
        Messages.server_line(server.name, online=True, group=server.group),
        metric("Model", cpu.model, icon="🧠"),
        metric("Cores", cpu.cores, icon="🔢"),
        metric("Suhu", cpu.temperature, icon="🌡️"),
        metric("Overall", f"{cpu.overall_usage}%", icon="⚡"),
    ]
    if detail:
        for index, usage in enumerate(cpu.usage_per_core):
            lines.append(f"  Core {index}: {progress_bar(usage)}")
        if cpu.top_processes:
            lines.append(italic("Top Processes (CPU)"))
            lines.extend(_process_rows(cpu.top_processes))
    return lines


async def _memory_block(
    connection: Connection,
    server: ServerConfig,
    detail: bool,
    reveal: bool,
) -> list[str]:
    """RAM and swap rows; cache/buffer and top processes only in detail mode."""
    mem = await collect_memory_details(connection)
    lines = [Messages.server_line(server.name, online=True, group=server.group)]
    if mem.total_mb > 0:
        usage = round(mem.used_mb / mem.total_mb * 100, 1)
        lines.extend(
            [
                metric("RAM", f"{mem.used_mb} / {mem.total_mb} MB", icon="💾"),
                f"  {progress_bar(usage)}",
                metric("Free", f"{mem.free_mb} MB", icon="🟢"),
                metric("Available", f"{mem.available_mb} MB", icon="📦"),
            ]
        )
    if mem.swap_total_mb > 0:
        swap_usage = round(mem.swap_used_mb / mem.swap_total_mb * 100, 1)
        lines.extend(
            [
                metric("Swap", f"{mem.swap_used_mb} / {mem.swap_total_mb} MB", icon="♻️"),
                f"  {progress_bar(swap_usage)}",
            ]
        )
    else:
        lines.append(metric("Swap", "tidak aktif", icon="♻️"))
    if detail:
        lines.append(metric("Cached", f"{mem.cached_mb} MB", icon="🗃️"))
        lines.append(metric("Buffers", f"{mem.buffers_mb} MB", icon="🧱"))
        if mem.top_processes:
            lines.append(italic("Top Processes (Memory)"))
            lines.extend(_process_rows(mem.top_processes, field="mem"))
    return lines


async def _network_block(
    connection: Connection,
    server: ServerConfig,
    detail: bool,
    reveal: bool,
) -> list[str]:
    """Traffic and connection rows; interfaces and ports only in detail mode."""
    net = await collect_network_details(connection)
    lines = [
        Messages.server_line(server.name, online=True, group=server.group),
        metric("Total RX", _format_bytes(net.total_rx_bytes), icon="⬇️"),
        metric("Total TX", _format_bytes(net.total_tx_bytes), icon="⬆️"),
        metric("Koneksi aktif", net.active_connections, icon="🔌"),
        metric("Established", net.established_connections, icon="🤝"),
    ]
    if not detail:
        return lines

    for iface in net.interfaces:
        if iface["name"] == "lo":
            continue
        lines.append(
            metric(
                f"Interface {iface['name']}",
                f"↓{_format_bytes(iface['rx_bytes'])} ↑{_format_bytes(iface['tx_bytes'])}",
                icon="🧭",
            )
        )
    if net.listening_ports:
        lines.append(italic("Listening Ports"))
        for port_info in net.listening_ports[:LISTENING_PORT_LIMIT]:
            process = port_info["process"] or "unknown"
            port_label = esc(f":{port_info['port']}")
            lines.append(f"  • {port_label} — {Messages.hidden_value(process, reveal)}")
    return lines


async def _disk_block(
    connection: Connection,
    server: ServerConfig,
    detail: bool,
    reveal: bool,
) -> list[str]:
    """Partition rows; inode usage and I/O counters only in detail mode."""
    disk = await collect_disk_details(connection)
    lines = [Messages.server_line(server.name, online=True, group=server.group)]
    for part in disk.partitions:
        usage = _parse_percent(part["use_percent"])
        lines.append(
            metric(f"Mount {part['mount']}", f"{part['used']} / {part['size']}", icon="💿")
        )
        lines.append(f"  {progress_bar(usage)}")
        if detail:
            lines.append(metric("Device", part["device"], icon="🔌"))
            lines.append(metric("Free", part["avail"], icon="🆓"))
    if detail and disk.total_inodes > 0:
        inode_usage = round(disk.used_inodes / disk.total_inodes * 100, 1)
        lines.append(metric("Inodes", f"{disk.used_inodes:,} / {disk.total_inodes:,}", icon="🔢"))
        lines.append(f"  {progress_bar(inode_usage)}")
        for stat in disk.io_stats:
            lines.append(
                metric(
                    f"I/O {stat['device']}",
                    f"R={stat['reads']:,} W={stat['writes']:,}",
                    icon="📊",
                )
            )
    return lines


async def _processes_block(
    connection: Connection,
    server: ServerConfig,
    detail: bool,
    reveal: bool,
) -> list[str]:
    """Top processes by CPU; memory ranking, totals, and zombies only in detail."""
    cpu_details = await collect_cpu_details(connection)
    lines = [Messages.server_line(server.name, online=True, group=server.group)]
    if cpu_details.top_processes:
        lines.append(italic("Top by CPU"))
        lines.extend(_process_rows(cpu_details.top_processes))
    if not detail:
        return lines

    mem_details = await collect_memory_details(connection)
    if mem_details.top_processes:
        lines.append(italic("Top by Memory"))
        lines.extend(_process_rows(mem_details.top_processes, field="mem"))

    total = await connection.run("ps aux | wc -l")
    if total.exit_code == 0:
        lines.append(metric("Total proses", max(0, int(total.stdout.strip()) - 1), icon="🧮"))
    zombies = await connection.run("ps aux | awk '$8 ~ /Z/ {count++} END {print count+0}'")
    if zombies.exit_code == 0 and int(zombies.stdout.strip() or 0) > 0:
        lines.append(metric("Zombie", int(zombies.stdout.strip()), icon="🧟"))
    return lines


def _process_rows(processes: list[dict], field: str = "cpu") -> list[str]:
    """Render top-process rows shared by the CPU, memory, and process screens."""
    rows = []
    for index, proc in enumerate(processes[:TOP_PROCESS_LIMIT], 1):
        command = str(proc.get("command", ""))[:45]
        rows.append(
            metric(
                f"{index}. PID {proc.get('pid', '?')}",
                f"{proc.get(field, '?')}% {command}",
                icon="↳",
            )
        )
    return rows


def _parse_percent(raw: str) -> float:
    """Parse a ``df`` percentage such as ``42%`` into a float."""
    try:
        return float(str(raw).replace("%", "").strip())
    except ValueError:
        return 0.0


SCREEN_BUILDERS: dict[str, BlockBuilder] = {
    "cpu": _cpu_block,
    "memory": _memory_block,
    "network": _network_block,
    "disk": _disk_block,
    "processes": _processes_block,
}

MONITOR_SCREENS: frozenset[str] = frozenset(SCREEN_BUILDERS)


def _monitor_menu_text() -> str:
    """Rich monitor menu: every screen with the collection method it uses."""
    methods = "\n".join(
        [
            Messages.METHOD_CPU_LINE,
            Messages.METHOD_MEMORY_LINE,
            Messages.METHOD_NETWORK_LINE,
            Messages.METHOD_DISK_LINE,
            Messages.METHOD_PROCESSES_LINE,
        ]
    )
    return (
        f"{Messages.MONITOR_HEADER}\n"
        f"<i>Pilih dashboard yang ingin dibuka dari keyboard di bawah.</i>\n"
        f"\n"
        f"<blockquote>{methods}</blockquote>"
    )


async def _show_screen(
    message: Message, state: FSMContext, services: Services, screen: str
) -> None:
    """Push the navigation state and send the requested monitor dashboard."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, screen)
    report = await render_screen_report(screen, servers=enabled)
    await send_report(message, report, reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command=f"/{screen}", action=f"monitor.{screen}")


@router.message(Command("monitor"))
@router.message(F.text == Messages.MENU_MONITOR)
async def cmd_monitor(message: Message, state: FSMContext, services: Services) -> None:
    """Show the monitor submenu."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "monitor")
    await message.answer(_monitor_menu_text(), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/monitor", action="monitor.menu")


@router.message(Command("cpu"))
@router.message(F.text == Messages.MENU_CPU)
async def cmd_cpu(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed CPU information."""
    await _show_screen(message, state, services, "cpu")


@router.message(Command("mem"))
@router.message(F.text == Messages.MENU_MEMORY)
async def cmd_memory(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed memory information."""
    await _show_screen(message, state, services, "memory")


@router.message(Command("net"))
@router.message(F.text == Messages.MENU_NETWORK)
async def cmd_network(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed network information."""
    await _show_screen(message, state, services, "network")


@router.message(Command("disk"))
@router.message(F.text == Messages.MENU_DISK)
async def cmd_disk(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed disk information."""
    await _show_screen(message, state, services, "disk")


@router.message(Command("proc"))
@router.message(F.text == Messages.MENU_PROCESSES)
async def cmd_processes(message: Message, state: FSMContext, services: Services) -> None:
    """Show top processes by CPU and memory."""
    await _show_screen(message, state, services, "processes")
