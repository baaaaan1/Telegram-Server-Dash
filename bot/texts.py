"""Text constants and messages for TSD Bot."""


class Messages:
    """Bot message templates - Indonesian and English bilingual."""

    # Start messages
    WELCOME_ID = "👋 Selamat datang di Telegram Server Dash!"
    WELCOME_EN = "👋 Welcome to Telegram Server Dash!"

    # Navigation
    BTN_HOME = "🏠 Home"
    BTN_BACK = "← Back"
    BTN_CANCEL = "✖ Cancel"
    BTN_REFRESH = "🔄 Refresh"

    # Menu
    MENU_STATUS = "📊 Status Server"
    MENU_PING = "🟢 Ping Server"
    MENU_HELP = "❓ Bantuan"
    MENU_CPU = "🖥️ CPU"
    MENU_MEMORY = "💾 Memory"
    MENU_NETWORK = "🌐 Network"
    MENU_PROCESSES = "⚙️ Processes"
    MENU_DISK = "💿 Disk"
    MENU_MONITOR = "📈 Monitor"

    # Status output
    STATUS_HEADER = "📊 <b>Server Status</b>\n"
    STATUS_OFFLINE = "⚠️ Server {name} tidak aktif\n{latency}ms"
    STATUS_ONLINE = "🟢 Server {name} aktif\n{latency}ms"
    STATUS_LOAD = "Load: {load}"
    STATUS_UPTIME = "Uptime: {uptime}"
    STATUS_MEMORY = "RAM: {ram}"
    STATUS_DISK = "Disk: {disk}"

    # Ping output
    PING_CONNECTIVITY = "🟢 Koneksi OK\n⏱️ Latensi: {time:.2f}ms"
    PING_FAIL = "🔴 Koneksi gagal\n{error}"

    # Help
    HELP_TEXT_ID = """<b>📋 Panduan Penggunaan</b>

/start - Mulai bot
/status - Cek status server
/ping - Uji konektivitas
/monitor - Menu monitoring
/cpu - Detail CPU
/mem - Detail memory
/net - Detail network
/disk - Detail disk
/proc - Top processes
/echo - Balas teks Anda

Menu navigasi:
🏠 Home - Kembali ke utama
← Back - Kembali ke layar sebelumnya
✖ Cancel - Batalkan operasi

Untuk bantuan lebih lanjut, ketuk ❓"""

    HELP_TEXT_EN = """<b>📋 User Guide</b>

/start - Start bot
/status - Check server status
/ping - Test connectivity
/monitor - Monitoring menu
/cpu - CPU details
/mem - Memory details
/net - Network details
/disk - Disk details
/proc - Top processes
/echo - Echo your text

Navigation:
🏠 Home - Go to main menu
← Back - Go back
✖ Cancel - Cancel operation

For more help, tap ❓"""

    # Unknown user
    ACCESS_DENIED = "❌ Akses ditolak. Anda tidak di whitelist admin."

    # Error
    ERROR_UNKNOWN = "❌ Terjadi kesalahan. Silakan coba lagi."

    # Monitoring headers
    CPU_HEADER = "🖥️ <b>CPU Details</b>\n"
    MEMORY_HEADER = "💾 <b>Memory Details</b>\n"
    NETWORK_HEADER = "🌐 <b>Network Details</b>\n"
    PROCESSES_HEADER = "⚙️ <b>Top Processes</b>\n"
    DISK_HEADER = "💿 <b>Disk Details</b>\n"
    MONITOR_HEADER = "📈 <b>System Monitor</b>\n"

    # Echo
    ECHO_PREFIX = "<i>Echo:</i>"


# Auth keys are stored in FSM data
NAV_KEYS = {
    "stack": "nav_stack",
    "back_stack": "nav_back",
}

# Cancel/Back/Home button labels (for keyboard detection)
NAV_BUTTONS = {
    "HOME": "🏠 Home",
    "BACK": "← Back",
    "CANCEL": "✖ Cancel",
}
