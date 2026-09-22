"""Monitoring handlers - detailed system monitoring (htop-like)."""

from __future__ import annotations

import asyncio
import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard, make_monitor_keyboard
from bot.nav import push_screen
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
from core.ssh import create_ssh_pool

router = Router()
logger = logging.getLogger(__name__)


def _format_bytes(b: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"


def _make_bar(percentage: float, width: int = 10) -> str:
    """Create a text-based progress bar."""
    filled = int(width * percentage / 100)
    empty = width - filled
    if percentage >= 90:
        return f"{'🟥' * filled}{'⬜' * empty}"
    elif percentage >= 70:
        return f"{'🟧' * filled}{'⬜' * empty}"
    else:
        return f"{'🟩' * filled}{'⬜' * empty}"


async def _load_enabled_servers(message: Message) -> dict[str, ServerConfig] | None:
    """Load servers enabled in the registry; access control runs in middleware."""
    _settings, config_path = load_settings()
    registry = load_server_registry(config_path)
    enabled = registry.get_enabled_servers()
    if not enabled:
        await message.answer(
            "ℹ️ Tidak ada server yang dikonfigurasi.", reply_markup=make_home_keyboard()
        )
        return None
    return enabled


@router.message(Command("monitor"))
@router.message(F.text == Messages.MENU_MONITOR)
async def cmd_monitor(message: Message, state: FSMContext, services: Services) -> None:
    """Show monitor submenu."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "monitor")
    await message.answer(
        "📈 <b>System Monitor</b>\n\nPilih monitoring yang ingin dilihat:",
        reply_markup=make_monitor_keyboard(),
    )
    await log_user_action(services, message, command="/monitor", action="monitor.menu")


@router.message(Command("cpu"))
@router.message(F.text == Messages.MENU_CPU)
async def cmd_cpu(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed CPU information."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "cpu")
    pool = create_ssh_pool(enabled)
    lines = [Messages.CPU_HEADER]

    try:
        for name, _server in enabled.items():
            connection = pool[name]
            try:
                cpu = await collect_cpu_details(connection)
            except Exception:
                logger.exception("Failed to collect CPU details for %s", name)
                lines.append(f"🔴 <b>{html.escape(name)}</b>: gagal mengambil data")
                continue

            safe_name = html.escape(name)
            lines.append(f"\n🟢 <b>{safe_name}</b>")
            lines.append(f"   Model: <code>{html.escape(cpu.model)}</code>")
            lines.append(f"   Cores: {cpu.cores}")
            lines.append(f"   Suhu: {cpu.temperature}")

            if cpu.usage_per_core:
                lines.append("\n   <b>CPU Usage per Core:</b>")
                for i, usage in enumerate(cpu.usage_per_core):
                    bar = _make_bar(usage)
                    lines.append(f"   Core {i}: {bar} {usage}%")

                lines.append(f"\n   <b>Overall: {cpu.overall_usage}%</b>")

            if cpu.top_processes:
                lines.append("\n   <b>Top Processes (CPU):</b>")
                for i, proc in enumerate(cpu.top_processes[:5], 1):
                    cmd = html.escape(proc["command"][:40])
                    lines.append(f"   {i}. <code>{proc['cpu']}%</code> - PID {proc['pid']} - {cmd}")
    finally:
        await asyncio.gather(*(c.close() for c in pool.values()), return_exceptions=True)

    await message.answer("\n".join(lines), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/cpu", action="monitor.cpu")


@router.message(Command("mem"))
@router.message(F.text == Messages.MENU_MEMORY)
async def cmd_memory(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed memory information."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "memory")
    pool = create_ssh_pool(enabled)
    lines = [Messages.MEMORY_HEADER]

    try:
        for name, _server in enabled.items():
            connection = pool[name]
            try:
                mem = await collect_memory_details(connection)
            except Exception:
                logger.exception("Failed to collect memory details for %s", name)
                lines.append(f"🔴 <b>{html.escape(name)}</b>: gagal mengambil data")
                continue

            safe_name = html.escape(name)
            lines.append(f"\n🟢 <b>{safe_name}</b>")

            if mem.total_mb > 0:
                usage_pct = round(mem.used_mb / mem.total_mb * 100, 1)
                bar = _make_bar(usage_pct)
                lines.append(f"\n   <b>RAM:</b> {bar} {usage_pct}%")
                lines.append(f"   Used: {mem.used_mb} MB / {mem.total_mb} MB")
                lines.append(f"   Free: {mem.free_mb} MB")
                lines.append(f"   Available: {mem.available_mb} MB")
                lines.append(f"   Cached: {mem.cached_mb} MB")
                lines.append(f"   Buffers: {mem.buffers_mb} MB")

            if mem.swap_total_mb > 0:
                swap_pct = round(mem.swap_used_mb / mem.swap_total_mb * 100, 1)
                bar = _make_bar(swap_pct)
                lines.append(f"\n   <b>Swap:</b> {bar} {swap_pct}%")
                lines.append(f"   Used: {mem.swap_used_mb} MB / {mem.swap_total_mb} MB")
                lines.append(f"   Free: {mem.swap_free_mb} MB")
            else:
                lines.append("\n   <b>Swap:</b> Tidak aktif")

            if mem.top_processes:
                lines.append("\n   <b>Top Processes (Memory):</b>")
                for i, proc in enumerate(mem.top_processes[:5], 1):
                    cmd = html.escape(proc["command"][:40])
                    lines.append(f"   {i}. <code>{proc['mem']}%</code> - PID {proc['pid']} - {cmd}")
    finally:
        await asyncio.gather(*(c.close() for c in pool.values()), return_exceptions=True)

    await message.answer("\n".join(lines), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/mem", action="monitor.memory")


@router.message(Command("net"))
@router.message(F.text == Messages.MENU_NETWORK)
async def cmd_network(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed network information."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "network")
    pool = create_ssh_pool(enabled)
    lines = [Messages.NETWORK_HEADER]

    try:
        for name, _server in enabled.items():
            connection = pool[name]
            try:
                net = await collect_network_details(connection)
            except Exception:
                logger.exception("Failed to collect network details for %s", name)
                lines.append(f"🔴 <b>{html.escape(name)}</b>: gagal mengambil data")
                continue

            safe_name = html.escape(name)
            lines.append(f"\n🟢 <b>{safe_name}</b>")

            lines.append("\n   <b>Total Traffic:</b>")
            lines.append(f"   ↓ RX: {_format_bytes(net.total_rx_bytes)}")
            lines.append(f"   ↑ TX: {_format_bytes(net.total_tx_bytes)}")

            lines.append("\n   <b>Connections:</b>")
            lines.append(f"   Active: {net.active_connections}")
            lines.append(f"   Established: {net.established_connections}")

            if net.interfaces:
                lines.append("\n   <b>Interfaces:</b>")
                for iface in net.interfaces:
                    if iface["name"] == "lo":
                        continue
                    rx = _format_bytes(iface["rx_bytes"])
                    tx = _format_bytes(iface["tx_bytes"])
                    lines.append(f"   • <code>{html.escape(iface['name'])}</code>: ↓{rx} ↑{tx}")

            if net.listening_ports:
                lines.append("\n   <b>Listening Ports:</b>")
                for port_info in net.listening_ports[:10]:
                    process = port_info["process"] or "unknown"
                    lines.append(f"   • :{port_info['port']} - {html.escape(process)}")
    finally:
        await asyncio.gather(*(c.close() for c in pool.values()), return_exceptions=True)

    await message.answer("\n".join(lines), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/net", action="monitor.network")


@router.message(Command("disk"))
@router.message(F.text == Messages.MENU_DISK)
async def cmd_disk(message: Message, state: FSMContext, services: Services) -> None:
    """Show detailed disk information."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "disk")
    pool = create_ssh_pool(enabled)
    lines = [Messages.DISK_HEADER]

    try:
        for name, _server in enabled.items():
            connection = pool[name]
            try:
                disk = await collect_disk_details(connection)
            except Exception:
                logger.exception("Failed to collect disk details for %s", name)
                lines.append(f"🔴 <b>{html.escape(name)}</b>: gagal mengambil data")
                continue

            safe_name = html.escape(name)
            lines.append(f"\n🟢 <b>{safe_name}</b>")

            if disk.partitions:
                lines.append("\n   <b>Partitions:</b>")
                for part in disk.partitions:
                    usage_str = part["use_percent"].replace("%", "")
                    try:
                        usage_pct = float(usage_str)
                    except ValueError:
                        usage_pct = 0
                    bar = _make_bar(usage_pct, 6)
                    lines.append(f"   <code>{html.escape(part['mount'])}</code>")
                    lines.append(f"   {bar} {part['use_percent']} - {part['used']}/{part['size']}")
                    lines.append(
                        f"   Device: {html.escape(part['device'])} | Free: {part['avail']}"
                    )

            if disk.total_inodes > 0:
                inode_pct = round(disk.used_inodes / disk.total_inodes * 100, 1)
                bar = _make_bar(inode_pct, 6)
                lines.append(f"\n   <b>Inodes:</b> {bar} {inode_pct}%")
                lines.append(f"   Used: {disk.used_inodes:,} / {disk.total_inodes:,}")

            if disk.io_stats:
                lines.append("\n   <b>I/O Stats:</b>")
                for stat in disk.io_stats:
                    lines.append(
                        f"   <code>{html.escape(stat['device'])}</code>: "
                        f"R={stat['reads']:,} W={stat['writes']:,}"
                    )
    finally:
        await asyncio.gather(*(c.close() for c in pool.values()), return_exceptions=True)

    await message.answer("\n".join(lines), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/disk", action="monitor.disk")


@router.message(Command("proc"))
@router.message(F.text == Messages.MENU_PROCESSES)
async def cmd_processes(message: Message, state: FSMContext, services: Services) -> None:
    """Show top processes by CPU and memory."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    await push_screen(state, "processes")
    pool = create_ssh_pool(enabled)
    lines = [Messages.PROCESSES_HEADER]

    try:
        for name, _server in enabled.items():
            connection = pool[name]
            try:
                cpu_details = await collect_cpu_details(connection)
                mem_details = await collect_memory_details(connection)
            except Exception:
                logger.exception("Failed to collect process details for %s", name)
                lines.append(f"🔴 <b>{html.escape(name)}</b>: gagal mengambil data")
                continue

            safe_name = html.escape(name)
            lines.append(f"\n🟢 <b>{safe_name}</b>")

            if cpu_details.top_processes:
                lines.append("\n   <b>Top by CPU:</b>")
                for i, proc in enumerate(cpu_details.top_processes[:5], 1):
                    cmd = html.escape(proc["command"][:45])
                    lines.append(f"   {i}. <code>{proc['cpu']}%</code> | PID {proc['pid']} | {cmd}")

            if mem_details.top_processes:
                lines.append("\n   <b>Top by Memory:</b>")
                for i, proc in enumerate(mem_details.top_processes[:5], 1):
                    cmd = html.escape(proc["command"][:45])
                    lines.append(f"   {i}. <code>{proc['mem']}%</code> | PID {proc['pid']} | {cmd}")

            # Get process count
            result = await connection.run("ps aux | wc -l")
            if result.exit_code == 0:
                count = int(result.stdout.strip()) - 1
                lines.append(f"\n   <b>Total Processes:</b> {count}")

            # Get zombie count
            result = await connection.run("ps aux | awk '$8 ~ /Z/ {count++} END {print count+0}'")
            if result.exit_code == 0:
                zombies = int(result.stdout.strip())
                if zombies > 0:
                    lines.append(f"   ⚠️ <b>Zombies:</b> {zombies}")
    finally:
        await asyncio.gather(*(c.close() for c in pool.values()), return_exceptions=True)

    await message.answer("\n".join(lines), reply_markup=make_monitor_keyboard())
    await log_user_action(services, message, command="/proc", action="monitor.processes")
