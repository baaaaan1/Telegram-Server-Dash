"""Rich HTML message templates for TSD Bot.

Every template stays inside the Bot API formatting grammar (``<b>``, ``<i>``,
``<u>``, ``<s>``, ``<span class="tg-spoiler">``, ``<a href>``, ``<tg-emoji>``,
``<tg-time>``, ``<code>``, ``<pre>`` and ``<blockquote>``) and keeps the entity
count per message low by styling whole blocks instead of every single word.

Dynamic values are never interpolated raw: the ``render_*`` helpers escape them
through :mod:`bot.formatting` before the entity wrap, so a server name or a
command output cannot inject markup.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.formatting import (
    Entity,
    bold,
    code,
    esc,
    italic,
    metric,
    pre_code,
    spoiler,
    underline,
)
from config.settings import PIN_MAX_LENGTH, PIN_MIN_LENGTH


@dataclass(frozen=True, slots=True)
class HelpPage:
    """One page of the paged help screen."""

    key: str
    title: str
    body: str


def _command_line(command: str, description: str) -> str:
    """Method description line: monospace command name plus italic purpose."""
    return f"{code(command)} — {italic(description)}"


_HELP_INTRO_ID = italic("Navigasi memakai Reply Keyboard; panel inline menyertai tiap laporan.")
_HELP_INTRO_EN = italic("Navigation uses the Reply Keyboard; each report ships an inline panel.")
_HELP_EXAMPLE = pre_code("/unlock 123456789\n/audit 25")
_PIN_FLOW_NOTE_ID = (
    "<blockquote>Aksi kritikal meminta konfirmasi "
    f"{bold('Ya')}/{bold('Batal')} lalu PIN bila "
    f"{code('PIN_TTL_SECONDS')} sudah lewat.</blockquote>"
)
_PIN_FLOW_NOTE_EN = (
    "<blockquote>Critical actions ask for "
    f"{bold('Ya')}/{bold('Batal')} confirmation and a PIN once "
    f"{code('PIN_TTL_SECONDS')} has elapsed.</blockquote>"
)
_ADMIN_NOTE_ID = (
    "<blockquote>Jalur ini memerlukan permission "
    f"{code('manage_users')} atau {code('view_audit')}.\n\n"
    f"{_HELP_EXAMPLE}</blockquote>"
)
_ADMIN_NOTE_EN = (
    "<blockquote>These routes require the "
    f"{code('manage_users')} or {code('view_audit')} permission.\n\n"
    f"{_HELP_EXAMPLE}</blockquote>"
)


def _render_help(title: str, pages: tuple[HelpPage, ...], intro: str) -> str:
    """Combine every help page into one message for the ``Semua`` inline view."""
    body = "\n\n".join(
        f"{bold(page.title)}\n<blockquote>{page.body}</blockquote>" for page in pages
    )
    return f"{title}\n{intro}\n\n{body}"


class Messages:
    """Bot message templates - Indonesian and English bilingual."""

    # Start messages
    WELCOME_ID = (
        "👋 <b>Selamat datang di Telegram Server Dash!</b>\n"
        "<i>Dashboard kontrol &amp; monitoring VPS langsung dari Telegram.</i>\n"
        "\n"
        "<blockquote>Pilih menu pada keyboard di bawah, atau ketik perintah seperti "
        "<code>/status</code>. Setiap laporan dilengkapi panel inline untuk "
        "segarkan, detail, dan salin data.</blockquote>\n"
        "\n"
        "<blockquote expandable><b>Yang bisa Anda lakukan</b>\n"
        "📊 Pantau CPU, RAM, disk, jaringan, dan proses\n"
        "🟢 Uji konektivitas dan latensi host\n"
        "🔐 Amankan aksi kritikal dengan PIN\n"
        "🧾 Telusuri audit trail setiap aksi\n"
        "\n"
        "<i>Ketuk blok ini untuk membuka atau menutupnya.</i></blockquote>\n"
        "\n"
        "🔑 PIN aksi kritikal disimpan sebagai hash, dan nilainya "
        f"{spoiler('tidak pernah dikirim balik ke chat')}."
    )
    WELCOME_EN = (
        "👋 <b>Welcome to Telegram Server Dash!</b>\n"
        "<i>Your VPS control &amp; monitoring dashboard, right inside Telegram.</i>\n"
        "\n"
        "<blockquote>Pick a menu on the keyboard below, or type a command such as "
        "<code>/status</code>. Every report ships with an inline panel to refresh, "
        "expand, and copy the data.</blockquote>\n"
        "\n"
        "<blockquote expandable><b>What you can do</b>\n"
        "📊 Watch CPU, RAM, disk, network, and processes\n"
        "🟢 Probe host connectivity and latency\n"
        "🔐 Gate critical actions behind a PIN\n"
        "🧾 Inspect the audit trail of every action\n"
        "\n"
        "<i>Tap this block to expand or collapse it.</i></blockquote>"
    )

    # Navigation
    BTN_HOME = "🏠 Home"
    BTN_BACK = "← Back"
    BTN_CANCEL = "✖ Cancel"
    BTN_REFRESH = "🔄 Refresh"
    BTN_YES = "✅ Ya"
    BTN_NO = "❌ Batal"
    BTN_NEXT = "Next →"

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
    STATUS_HEADER = "📊 <b>Server Status</b>"
    STATUS_OFFLINE = "⚠️ Server {name} tidak aktif\n{latency}ms"
    STATUS_ONLINE = "🟢 Server {name} aktif\n{latency}ms"
    STATUS_LOAD = "Load: {load}"
    STATUS_UPTIME = "Uptime: {uptime}"
    STATUS_MEMORY = "RAM: {ram}"
    STATUS_DISK = "Disk: {disk}"

    # Ping output
    PING_CONNECTIVITY = "🟢 Koneksi OK\n⏱️ Latensi: {time:.2f}ms"
    PING_FAIL = "🔴 Koneksi gagal\n{error}"

    # Screen titles (inline-panel header + report headings)
    SCREEN_STATUS = "📊 <b>Status Server</b>"
    SCREEN_PING = "🟢 <b>Ping Server</b>"
    SCREEN_MONITOR = "📈 <b>System Monitor</b>"
    SCREEN_CPU = "🖥️ <b>CPU Details</b>"
    SCREEN_MEMORY = "💾 <b>Memory Details</b>"
    SCREEN_NETWORK = "🌐 <b>Network Details</b>"
    SCREEN_DISK = "💿 <b>Disk Details</b>"
    SCREEN_PROCESSES = "⚙️ <b>Top Processes</b>"
    SCREEN_HELP = "📚 <b>Panduan TSD Bot</b>"
    SCREEN_ECHO = "✍️ <b>Echo</b>"

    SCREEN_TITLES: dict[str, str] = {
        "home": WELCOME_ID,
        "status": SCREEN_STATUS,
        "ping": SCREEN_PING,
        "monitor": SCREEN_MONITOR,
        "cpu": SCREEN_CPU,
        "memory": SCREEN_MEMORY,
        "network": SCREEN_NETWORK,
        "disk": SCREEN_DISK,
        "processes": SCREEN_PROCESSES,
        "help": SCREEN_HELP,
        "echo": SCREEN_ECHO,
    }

    # Navigation header sent above every inline-panel report (Reply Keyboard guard)
    NAV_HEADER = "🧭 {title}\n<blockquote>{hint}</blockquote>"
    NAV_HINT_REPLY_KEYBOARD = (
        "Tombol <b>Cancel</b>, <b>Back</b>, dan <b>Home</b> tetap tersedia di keyboard bawah."
    )
    NAV_HINT_PANEL = "Panel inline di bawah mengubah laporan ini tanpa mengirim pesan baru."

    # Report fragments
    REPORT_NO_SERVERS = "ℹ️ Tidak ada server yang dikonfigurasi."
    REPORT_EMPTY_PAGE = "ℹ️ Tidak ada data pada halaman ini."
    REPORT_STALE = "⚠️ Angka di bawah berasal dari pemeriksaan terakhir yang berhasil."
    REPORT_SERVER_ONLINE = "🟢 <b>{name}</b>"
    REPORT_SERVER_OFFLINE = "🔴 <b>{name}</b>"
    REPORT_UNREACHABLE = "Status: <i>tidak dapat dijangkau</i>"
    REPORT_GROUP_TAG = " <i>({group})</i>"
    REPORT_PAGE = "Halaman <b>{page}</b>/<b>{pages}</b> · <i>{total} server</i>"
    REPORT_DETAIL_TOGGLE_HINT = "Mode detail menampilkan seluruh metrik yang tersedia."
    REPORT_REVEAL_TOGGLE_HINT = "Nilai sensitif disembunyikan sampai Anda membukanya."

    # Inline overlay labels
    INLINE_REFRESH = "🔄 Segarkan"
    INLINE_DETAIL_MORE = "🧩 Detail"
    INLINE_DETAIL_LESS = "🧩 Ringkas"
    INLINE_REVEAL_SHOW = "👁️ Buka"
    INLINE_REVEAL_HIDE = "🙈 Tutup"
    INLINE_COPY = "📋 Salin"
    INLINE_DOCS = "🌐 Dokumentasi"
    INLINE_PREV = "◀"
    INLINE_NEXT = "▶"
    INLINE_PAGE_INDICATOR = "{page}/{pages}"
    INLINE_PAGE_ALL = "📚 Semua"
    INLINE_HELP_ALL = "📚 Semua bagian"
    INLINE_QUICK_STATUS = "⚡ Status"
    INLINE_QUICK_PING = "📡 Ping"
    INLINE_QUICK_HELP = "📚 Bantuan"
    INLINE_QUICK_HOME = "🏠 Ringkasan"

    # Welcome-screen quick panel
    INLINE_HOME_PANEL = (
        "🚀 <b>Aksi cepat</b>\n"
        "<blockquote>Panel ini bisa berubah menjadi laporan: pilih satu tombol, lalu isinya "
        "diganti di tempat tanpa mengirim pesan baru.</blockquote>"
    )

    # Inline overlay toasts (callback answers)
    TOAST_REFRESHED = "🔄 Data diperbarui"
    TOAST_DETAIL_ON = "🧩 Mode detail aktif"
    TOAST_DETAIL_OFF = "🧩 Kembali ke mode ringkas"
    TOAST_REVEAL_ON = "👁️ Nilai sensitif ditampilkan"
    TOAST_REVEAL_OFF = "🙈 Nilai sensitif disembunyikan"
    TOAST_PAGE = "Halaman {page}"
    TOAST_HELP_ALL = "📚 Menampilkan seluruh panduan"
    TOAST_STALE = "⚠️ Pesan ini tidak dapat diperbarui lagi. Kirim ulang perintahnya."
    TOAST_UNKNOWN = "⚠️ Aksi panel tidak dikenal."
    TOAST_FOREIGN = "⚠️ Panel ini milik pengguna lain."
    TOAST_BUSY = "⏳ Tunggu sebentar lalu coba lagi."
    TOAST_UNCHANGED = "✅ Tidak ada perubahan data"

    # Monitoring headers
    CPU_HEADER = SCREEN_CPU
    MEMORY_HEADER = SCREEN_MEMORY
    NETWORK_HEADER = SCREEN_NETWORK
    PROCESSES_HEADER = SCREEN_PROCESSES
    DISK_HEADER = SCREEN_DISK
    MONITOR_HEADER = SCREEN_MONITOR

    # Help (paged inline view)
    HELP_PAGES_ID: tuple[HelpPage, ...] = (
        HelpPage(
            key="monitoring",
            title="📊 Monitoring",
            body="\n".join(
                [
                    f"📊 {_command_line('/status', 'ringkasan host: uptime, load, RAM, disk')}",
                    f"🟢 {_command_line('/ping', 'uji konektivitas dan latensi')}",
                    f"📈 {_command_line('/monitor', 'menu monitoring lanjutan')}",
                    f"🖥️ {_command_line('/cpu', 'pemakaian per core, suhu, proses teratas')}",
                    f"💾 {_command_line('/mem', 'RAM, swap, cache, proses teratas')}",
                    f"🌐 {_command_line('/net', 'trafik, koneksi, port yang mendengarkan')}",
                    f"💿 {_command_line('/disk', 'partisi, inode, dan statistik I/O')}",
                    f"⚙️ {_command_line('/proc', 'proses teratas dan jumlah zombie')}",
                ]
            ),
        ),
        HelpPage(
            key="account",
            title="🔐 Akun & Keamanan",
            body="\n".join(
                [
                    f"👤 {_command_line('/whoami', 'ID, role, izin, status PIN dan lockout')}",
                    f"🔑 {_command_line('/pin', f'atur PIN {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digit untuk aksi kritikal')}",
                    f"✍️ {_command_line('/echo', 'uji balasan teks')}",
                    f"✖ {_command_line('/cancel', 'batalkan alur yang sedang berjalan')}",
                    "",
                    _PIN_FLOW_NOTE_ID,
                ]
            ),
        ),
        HelpPage(
            key="admin",
            title="🛡️ Admin",
            body="\n".join(
                [
                    f"🔓 {_command_line('/unlock <user_id>', 'bersihkan lockout user')}",
                    f"👥 {_command_line('/users', 'daftar user terdaftar beserta role')}",
                    f"🧾 {_command_line('/audit [n]', 'n (maks 25) entri audit terakhir')}",
                    "",
                    _ADMIN_NOTE_ID,
                ]
            ),
        ),
    )

    HELP_PAGES_EN: tuple[HelpPage, ...] = (
        HelpPage(
            key="monitoring",
            title="📊 Monitoring",
            body="\n".join(
                [
                    f"📊 {_command_line('/status', 'host summary: uptime, load, RAM, disk')}",
                    f"🟢 {_command_line('/ping', 'connectivity and latency probe')}",
                    f"📈 {_command_line('/monitor', 'advanced monitoring menu')}",
                    f"🖥️ {_command_line('/cpu', 'per-core usage, temperature, top processes')}",
                    f"💾 {_command_line('/mem', 'RAM, swap, cache, top processes')}",
                    f"🌐 {_command_line('/net', 'traffic, connections, listening ports')}",
                    f"💿 {_command_line('/disk', 'partitions, inodes, I/O statistics')}",
                    f"⚙️ {_command_line('/proc', 'top processes and zombie count')}",
                ]
            ),
        ),
        HelpPage(
            key="account",
            title="🔐 Account & Security",
            body="\n".join(
                [
                    f"👤 {_command_line('/whoami', 'ID, role, permissions, PIN and lockout state')}",
                    f"🔑 {_command_line('/pin', f'set a {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digit PIN for critical actions')}",
                    f"✍️ {_command_line('/echo', 'test text replies')}",
                    f"✖ {_command_line('/cancel', 'abort the running flow')}",
                    "",
                    _PIN_FLOW_NOTE_EN,
                ]
            ),
        ),
        HelpPage(
            key="admin",
            title="🛡️ Admin",
            body="\n".join(
                [
                    f"🔓 {_command_line('/unlock <user_id>', 'clear a user lockout')}",
                    f"👥 {_command_line('/users', 'list registered users and roles')}",
                    f"🧾 {_command_line('/audit [n]', 'last n (max 25) audit entries')}",
                    "",
                    _ADMIN_NOTE_EN,
                ]
            ),
        ),
    )

    HELP_TEXT_ID = _render_help(SCREEN_HELP, HELP_PAGES_ID, _HELP_INTRO_ID)
    HELP_TEXT_EN = _render_help(SCREEN_HELP, HELP_PAGES_EN, _HELP_INTRO_EN)

    # Access control (Task 1)
    ACCESS_DENIED = "❌ Akses ditolak. ID Anda tidak terdaftar sebagai pengguna bot."
    ACCESS_INACTIVE = "❌ Akses Anda dinonaktifkan oleh admin."
    ACCESS_USERNAME_MISMATCH = (
        "❌ Akses ditolak. Username akun ini tidak cocok dengan whitelist admin."
    )
    ACCESS_LOCKED = "🔒 Akses dikunci sementara. Coba lagi dalam {minutes} menit."
    RATE_LIMITED = "⏳ Terlalu banyak permintaan. Tunggu {seconds} detik lalu coba lagi."
    PERMISSION_DENIED = "🚫 Anda tidak memiliki izin untuk aksi ini."
    ADMIN_ACCESS_ALERT = (
        "🚨 <b>Percobaan akses ditolak</b>\n"
        "\n"
        "<blockquote>"
        "User: {who}\n"
        "ID: <code>{user_id}</code>\n"
        "Status: <b>{status}</b>\n"
        "Pesan: <code>{command}</code>"
        "</blockquote>"
    )

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

    CONFIRM_ACTION = "⚠️ <b>{title}</b>\n\nServer: <code>{server}</code>\nLanjutkan?"
    CONFIRM_CHOICE_ONLY = "ℹ️ Pilih ✅ Ya atau ❌ Batal."
    ACTION_DONE = "✅ Aksi <b>{title}</b> selesai."
    ACTION_CANCELLED = "✅ Aksi dibatalkan."

    # Account info
    WHOAMI = "👤 <b>Info Akun</b>\n\nID: <code>{user_id}</code>\nUsername: {username}\nBinding: {binding}\nRole: <b>{role}</b>\nPIN: {pin_status}\nLockout: {lock_status}\n\nIzin: {permissions}"

    # Navigation feedback
    BACK_TO = "← Kembali ke <b>{screen}</b>"
    BACK_AT_ROOT = "ℹ️ Anda sudah di halaman utama."

    # Admin utilities
    UNLOCK_OK = "🔓 Lockout user <code>{user_id}</code> dibersihkan."
    UNLOCK_UNKNOWN = "❌ User <code>{user_id}</code> tidak terdaftar."
    UNLOCK_USAGE = "ℹ️ Gunakan: /unlock &lt;user_id&gt;"
    USERS_HEADER = "👥 <b>User Terdaftar</b>\n"
    USERS_EMPTY = "ℹ️ Belum ada user terdaftar."
    AUDIT_HEADER = "🧾 <b>Audit Terakhir</b>\n"
    AUDIT_EMPTY = "ℹ️ Belum ada entri audit."
    AUDIT_LINE = "#{id} <code>{timestamp}</code> | {user} | {action} | {result}"

    # Echo
    ECHO_PREFIX = "<i>Echo:</i>"

    # Method descriptions shown next to command output
    METHOD_STATUS_LINE = "Metode: <i>uptime, load average, /proc/meminfo, df</i>"
    METHOD_PING_LINE = "Metode: <i>probe koneksi + pengukuran latensi</i>"
    METHOD_CPU_LINE = "Metode: <i>/proc/stat per core, sensors, ps</i>"
    METHOD_MEMORY_LINE = "Metode: <i>/proc/meminfo, ps sortir memori</i>"
    METHOD_NETWORK_LINE = "Metode: <i>/proc/net/dev, ss, resolusi port</i>"
    METHOD_DISK_LINE = "Metode: <i>df, inode stat, /proc/diskstats</i>"
    METHOD_PROCESSES_LINE = "Metode: <i>ps aux, penghitungan zombie</i>"

    @staticmethod
    def nav_header(screen: str, hint: str = NAV_HINT_REPLY_KEYBOARD) -> str:
        """Navigation header carrying screen title plus the Reply Keyboard reminder."""
        title = Messages.SCREEN_TITLES.get(screen, Messages.SCREEN_STATUS)
        return Messages.NAV_HEADER.format(title=title, hint=esc(hint))

    @staticmethod
    def report_heading(screen: str, method_line: str = "") -> str:
        """Report heading combining the screen title with its collection method."""
        title = Messages.SCREEN_TITLES.get(screen, Messages.SCREEN_STATUS)
        if not method_line:
            return title
        return f"{title}\n<blockquote>{method_line}</blockquote>"

    @staticmethod
    def server_line(name: str, *, online: bool, group: str | None = None) -> str:
        """Escaped server heading with an optional group tag."""
        icon = Messages.REPORT_SERVER_ONLINE if online else Messages.REPORT_SERVER_OFFLINE
        tag = Messages.REPORT_GROUP_TAG.format(group=esc(group)) if group else ""
        return icon.format(name=esc(name)) + tag

    @staticmethod
    def server_details(  # noqa: PLR0913 - explicit metric fields keep call sites readable
        hostname: str,
        uptime: str,
        load: str,
        memory: str,
        disk: str,
        *,
        reveal: bool = False,
    ) -> str:
        """Metric rows for one online host (each row uses a single bold entity)."""
        return "\n".join(
            [
                metric("Hostname", Messages.hidden_value(hostname, reveal), icon="🏷️"),
                metric("Uptime", uptime, icon="⏱️"),
                metric("Load 1/5/15m", load, icon="📈"),
                metric("RAM", memory, icon="💾"),
                metric("Disk /", disk, icon="💿"),
            ]
        )

    @staticmethod
    def detail_row(label: str, value: object, *, icon: str = "🔎") -> str:
        """Extra row only shown in detail mode."""
        return metric(label, value, icon=icon)

    @staticmethod
    def latency_row(latency_ms: float, *, online: bool = True) -> str:
        """Latency row; negative values are reported as unavailable."""
        if not online or latency_ms < 0:
            return metric("Latensi", "n/a", icon="⏱️")
        return metric("Latensi", f"{latency_ms:.2f} ms", icon="⏱️")

    @staticmethod
    def hidden_value(value: object, reveal: bool) -> Entity:
        """Reveal-or-spoiler wrapper for sensitive values such as host addresses.

        The value is escaped either way: a revealed value is still untrusted data.
        """
        return Entity(esc(value)) if reveal else Entity(spoiler(value))

    @staticmethod
    def context_hint(*, detail: bool, reveal: bool) -> str:
        """Explain what the active inline toggles are doing to this report."""
        notes: list[str] = []
        if detail:
            notes.append(Messages.REPORT_DETAIL_TOGGLE_HINT)
        if reveal:
            notes.append(Messages.REPORT_REVEAL_TOGGLE_HINT)
        if not notes:
            return ""
        return "\n" + "\n".join(italic(note) for note in notes)

    @staticmethod
    def command_description(command: str, description: str) -> str:
        """One method description: monospace command name plus italic purpose."""
        return _command_line(command, description)

    @staticmethod
    def emphasized(text: str) -> str:
        """Underlined emphasis for key instructions."""
        return underline(text)


NAV_KEYS = {
    "stack": "nav_stack",
    "back_stack": "nav_back",
}

NAV_BUTTONS = {
    "HOME": "🏠 Home",
    "BACK": "← Back",
    "CANCEL": "✖ Cancel",
}
