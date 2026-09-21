"""Text constants and messages for TSD Bot."""

from config.settings import PIN_MAX_LENGTH, PIN_MIN_LENGTH


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
    BTN_YES = "✅ Ya"
    BTN_NO = "❌ Batal"

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
/whoami - Info akun & role Anda
/pin - Atur / ganti PIN aksi kritikal

Admin:
/unlock &lt;user_id&gt; - Buka lockout user
/users - Daftar user terdaftar
/audit - 10 entri audit terakhir

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
/whoami - Your account & role
/pin - Set / change critical-action PIN

Admin:
/unlock &lt;user_id&gt; - Clear user lockout
/users - List registered users
/audit - Last 10 audit entries

Navigation:
🏠 Home - Go to main menu
← Back - Go back
✖ Cancel - Cancel operation

For more help, tap ❓"""

    # Access control (Task 1)
    ACCESS_DENIED = "❌ Akses ditolak. ID Anda tidak terdaftar sebagai pengguna bot."
    ACCESS_INACTIVE = "❌ Akses Anda dinonaktifkan oleh admin."
    ACCESS_USERNAME_MISMATCH = (
        "❌ Akses ditolak. Username akun ini tidak cocok dengan whitelist admin."
    )
    ACCESS_LOCKED = "🔒 Akses dikunci sementara. Coba lagi dalam {minutes} menit."
    RATE_LIMITED = "⏳ Terlalu banyak permintaan. Tunggu {seconds} detik lalu coba lagi."
    PERMISSION_DENIED = "🚫 Anda tidak memiliki izin untuk aksi ini."
    ADMIN_ACCESS_ALERT = """🚨 <b>Percobaan akses ditolak</b>

User: {who}
ID: <code>{user_id}</code>
Status: <b>{status}</b>
Pesan: <code>{command}</code>"""

    # Error
    ERROR_UNKNOWN = "❌ Terjadi kesalahan. Silakan coba lagi."

    # Critical action PIN (Task 1)
    PIN_PROMPT = "🔑 Masukkan PIN untuk melanjutkan aksi kritikal ini."
    PIN_WRONG = "❌ PIN salah. Sisa percobaan: {remaining}."
    PIN_NOT_SET = "ℹ️ PIN belum diatur. Atur dengan /pin terlebih dahulu."
    PIN_VERIFIED = "✅ PIN terverifikasi."
    PIN_ENV_HINT = "ℹ️ PIN saat ini berasal dari TSD_PIN; PIN baru akan menggantikannya."
    PIN_SETUP_CURRENT = "🔑 Masukkan PIN saat ini."
    PIN_SETUP_NEW = f"🔑 Masukkan PIN baru ({PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digit angka)."
    PIN_SETUP_CONFIRM = "🔁 Ulangi PIN baru untuk konfirmasi."
    PIN_SETUP_INVALID = f"❌ PIN harus {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digit angka."
    PIN_SETUP_MISMATCH = "❌ Konfirmasi tidak sama. Masukkan PIN baru lagi."
    PIN_SETUP_DONE = "✅ PIN berhasil disimpan."
    PIN_SETUP_CANCELLED = "✅ Pengaturan PIN dibatalkan."

    CONFIRM_ACTION = """⚠️ <b>{title}</b>

Server: <code>{server}</code>
Lanjutkan?"""
    CONFIRM_CHOICE_ONLY = "ℹ️ Pilih ✅ Ya atau ❌ Batal."
    ACTION_DONE = "✅ Aksi <b>{title}</b> selesai."
    ACTION_CANCELLED = "✅ Aksi dibatalkan."

    # Account info
    WHOAMI = """👤 <b>Info Akun</b>

ID: <code>{user_id}</code>
Username: {username}
Binding: {binding}
Role: <b>{role}</b>
PIN: {pin_status}
Lockout: {lock_status}

Izin: {permissions}"""

    # Admin utilities
    UNLOCK_OK = "🔓 Lockout user <code>{user_id}</code> dibersihkan."
    UNLOCK_UNKNOWN = "❌ User <code>{user_id}</code> tidak terdaftar."
    UNLOCK_USAGE = "ℹ️ Gunakan: /unlock &lt;user_id&gt;"
    USERS_HEADER = "👥 <b>User Terdaftar</b>\n"
    USERS_EMPTY = "ℹ️ Belum ada user terdaftar."
    AUDIT_HEADER = "🧾 <b>Audit Terakhir</b>\n"
    AUDIT_EMPTY = "ℹ️ Belum ada entri audit."
    AUDIT_LINE = "#{id} <code>{timestamp}</code> | {user} | {action} | {result}"

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
