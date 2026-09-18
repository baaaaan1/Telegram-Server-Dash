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
