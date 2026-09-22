# Telegram Server Dash

Telegram Server Dash (TSD) adalah bot Telegram berbasis aiogram untuk monitoring VPS. MVP saat ini ditujukan untuk satu host: bot berjalan langsung sebagai service systemd dan `transport: local` membaca informasi VPS melalui utilitas Linux dan `/proc`.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Status Proyek

Fondasi bot, navigasi, registry server, probe, SQLite, dan deployment native telah tersedia. Autentikasi whitelist, RBAC, PIN aksi kritikal, rate limiting, dan audit trail sudah aktif (lihat §1 [`TASKS.md`](TASKS.md)). Alerting dan operasi manajemen privileged masih berada dalam roadmap.

## Deployment Produksi

Host yang didukung adalah Ubuntu atau Debian dengan `apt`, systemd, dan Python 3.11+ dari repository distribusi (misalnya Ubuntu 24.04+ atau Debian 12+). Jalankan setup dari clone repository:

```bash
git clone https://github.com/baaaaan1/telegram-server-dash.git
cd telegram-server-dash
sudo ./setup.sh install
```

Installer akan:

- Memasang Python, virtualenv, Git, `ping`, dan utilitas proses yang dibutuhkan.
- Membuat system user terkunci `tsd`.
- Menyalin aplikasi dan virtualenv ke `/opt/telegram-server-dash`.
- Menyimpan environment rahasia di `/etc/telegram-server-dash/telegram-server-dash.env`.
- Menyimpan registry server di `/etc/telegram-server-dash/config.yaml`.
- Menyimpan SQLite di `/var/lib/telegram-server-dash/bot.db`.
- Mengaktifkan dan menjalankan `telegram-server-dash.service` dengan long polling.

`setup.sh install` meminta `BOT_TOKEN` tanpa echo dan minimal satu Telegram admin ID. Ketika dijalankan ulang, nilai yang ada dipertahankan jika input dibiarkan kosong. Installer tidak membuka port karena aplikasi produksi tidak menggunakan webhook.

### Konfigurasi Server

Konfigurasi awal memakai host lokal:

```yaml
servers:
  - name: local-vps
    group: production
    description: "VPS host running Telegram Server Dash"
    enabled: true
    transport: local
    monitor_interval: 30
```

Edit `/etc/telegram-server-dash/config.yaml`, kemudian jalankan:

```bash
sudo ./setup.sh configure
```

`transport: local` tepat untuk deployment ini karena proses Python berjalan native pada VPS yang dimonitor. Memindahkan service ke container akan membuat probe melihat lingkungan container, bukan host.

### Perintah Lifecycle

```bash
sudo ./setup.sh install
sudo ./setup.sh update
sudo ./setup.sh configure
sudo ./setup.sh status
sudo ./setup.sh logs
sudo ./setup.sh uninstall
sudo ./setup.sh uninstall --purge
```

- `install`: install atau repair deployment dan meminta konfigurasi runtime.
- `update`: memperbarui salinan aplikasi/dependency tanpa menimpa `/etc` atau `/var/lib`.
- `configure`: memperbarui token/admin ID secara interaktif dan me-restart service.
- `status`: menampilkan status systemd dan log terbaru.
- `logs`: mengikuti journal service.
- `uninstall`: menghapus service dan `/opt`, tetapi mempertahankan konfigurasi/data.
- `uninstall --purge`: juga menghapus konfigurasi/data setelah konfirmasi eksplisit.

#### Tampilan CLI

Setiap perintah yang berjalan di TTY menampilkan header bergaya, progress bertahap
(`[##....] 3/8  Validating the release`), spinner untuk proses panjang, panel ringkasan
berbentuk kotak, tabel, dan blok error yang menyebut langkah, perintah, exit code, serta
lokasi baris yang gagal. Presentasi diatur oleh `deploy/lib/ui.sh`.

Pemisahan stream dijaga agar output aman di-pipe:

- **stderr** untuk chrome: banner, progress, spinner, diagnostik, dan error.
- **stdout** untuk data: panel ringkasan, tabel, dan output journal.

```bash
sudo ./setup.sh status > status.txt   # data tetap bersih tanpa banner maupun progress
```

Opsi global yang tersedia untuk semua perintah:

```bash
sudo ./setup.sh --help
sudo ./setup.sh --version
sudo ./setup.sh --no-color status    # matikan warna ANSI
sudo ./setup.sh --plain status       # tanpa warna, glyph unicode, dan animasi
sudo ./setup.sh --no-animation install
sudo ./setup.sh --no-banner install
```

Variabel lingkungan yang setara: `NO_COLOR`, `TSD_NO_COLOR`, `TSD_PLAIN`, `TSD_ASCII`,
`TSD_NO_ANIMATION`, dan `TSD_NO_BANNER`. Warna, glyph unicode, dan animasi hanya aktif
pada TTY yang mendukung; ketika output dialihkan ke file, ke journald, atau ke CI, CLI
otomatis memakai output ASCII tanpa escape sequence.

Update kode produksi dilakukan dari checkout:

```bash
git pull --ff-only
sudo ./setup.sh update
```

### Log dan Diagnostik

```bash
sudo systemctl status telegram-server-dash.service
sudo journalctl -u telegram-server-dash.service -n 100 --no-pager
sudo journalctl -u telegram-server-dash.service -f
```

Service tidak memiliki HTTP health endpoint. Kondisi sehat dinilai dari status proses systemd dan journal.

### Backup

Cadangkan dua target berikut sebelum update besar atau migrasi:

```text
/etc/telegram-server-dash/
/var/lib/telegram-server-dash/bot.db
```

Hentikan service atau gunakan mekanisme backup SQLite yang konsisten sebelum menyalin database aktif.

## Autentikasi, RBAC & PIN

Setiap pesan private melewati `AccessMiddleware` sebelum mencapai handler: user harus terdaftar di whitelist, aktif, dan tidak sedang terkunci. Tanpa user terdaftar semua akses ditolak.

| Role | Kemampuan |
|---|---|
| `viewer` | Monitoring read-only (`/status`, `/ping`, `/monitor`, dll.). |
| `operator` | Semua viewer + manajemen service dan exec command (dipakai fitur §3). |
| `admin` | Semua permission, termasuk `/unlock`, `/users`, `/audit`, dan aksi kritikal. |

Whitelist diisi dari `ADMIN_USER_IDS`, `OPERATOR_USER_IDS`, dan `VIEWER_USER_IDS` saat service start, lalu disimpan di tabel `users` (PIN dan status lockout tidak tertimpa). Daftar env bersifat otoritatif: ID yang dihapus dari env akan dinonaktifkan otomatis pada restart berikutnya, dan ID yang ditambahkan kembali langsung aktif. `setup.sh install`/`configure` mempertahankan variabel opsional (`OPERATOR_USER_IDS`, `VIEWER_USER_IDS`, `STRICT_USERNAME_MATCH`, `TSD_PIN`, dan batas auth/rate limit) yang sudah ada di env file. User baru yang mencoba mengakses bot akan ditolak, dicatat di audit trail, dan admin menerima notifikasi (maksimal sekali per 10 menit per user).

### Verifikasi ID + Username

Setiap entri whitelist boleh mengikat akun ke username Telegram-nya dengan format `ID:username`. Jika binding ada, pesan hanya diterima ketika ID **dan** username cocok (perbandingan tanpa `@` dan tidak case-sensitive); username yang berubah atau tidak ada akan ditolak dan dicatat sebagai `auth.denied.username_mismatch`.

```env
ADMIN_USER_IDS=123456789:namauser,987654321
```

- `123456789:namauser` → hanya akun dengan ID tersebut dan username `@namauser`.
- `987654321` → hanya dicek ID-nya (kompatibel dengan konfigurasi lama).
- `STRICT_USERNAME_MATCH=1` mewajibkan **semua** entri whitelist punya binding username; service menolak start dengan pesan jelas jika ada yang belum diikat. Ini memberi jaminan bahwa akses hanya bisa oleh admin/master dengan ID + username yang cocok.
- Saat strict mode nonaktif, admin tanpa binding tetap bisa masuk tetapi dicatat sebagai peringatan di journal agar bisa diikat.
- Binding juga ditampilkan di `/whoami` (`Binding: terikat @namauser`) dan `/users` (`terikat: @namauser`).

Perintah terkait:

```text
/pin                 atur atau ganti PIN aksi kritikal (4-8 digit angka)
/whoami              tampilkan ID, role, permission, status PIN & lockout
/unlock <user_id>    admin: bersihkan lockout user
/users               admin: daftar user terdaftar
/audit [n]           admin: n (maks 25) entri audit terakhir
```

Aksi kritikal (reboot, kill proses, hapus file, ubah firewall) nanti dijalankan lewat `handlers/critical.py`: konfirmasi `✅ Ya` / `❌ Batal`, lalu PIN bila `PIN_TTL_SECONDS` sudah lewat. PIN disimpan sebagai hash PBKDF2-SHA256 di SQLite; `TSD_PIN` hanya fallback awal sebelum PIN diatur lewat `/pin`.

Rate limiting membatasi `RATE_LIMIT_PER_MINUTE` pesan per user per menit (tombol navigasi dikecualikan). Setelah `AUTH_MAX_ATTEMPTS` kegagalan PIN beruntun, akun terkunci `AUTH_LOCKOUT_SECONDS`. Jika admin utama ikut terkunci, pulihkan lewat `/unlock` dari admin lain atau buka database:

```bash
sudo -u tsd sqlite3 /var/lib/telegram-server-dash/bot.db \
  "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = <ID>;"
```

Semua aksi tercatat di tabel `audit_log` (user, command, server, waktu, hasil). Bila `LOG_CHAT_ID` diisi, salinan dikirim ke chat tersebut.

## Permission Model

Service berjalan sebagai user `tsd`, bukan root. Akses tulis service dibatasi ke `/var/lib/telegram-server-dash`; aplikasi dan konfigurasi bersifat read-only bagi service. Monitoring host yang tidak memerlukan privilege dapat berjalan langsung, tetapi beberapa detail sistem mungkin tidak tersedia bagi user biasa.

Fitur manajemen privileged di masa depan harus memakai aturan sudoers sempit per command dengan validasi input dan audit. Jangan menjalankan seluruh bot sebagai root dan jangan memberikan blanket passwordless sudo.

Unit saat ini memakai `NoNewPrivileges=true`. Ketika fitur privileged ditambahkan, hardening ini harus ditinjau secara eksplisit bersama aturan sudoers per-command; jangan sekadar menonaktifkannya tanpa threat review.

## Development

Gunakan Python 3.11 atau lebih baru:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Untuk development lokal, ubah `.env` agar memakai path repository:

```env
BOT_TOKEN=your:bot:token:here
ADMIN_USER_IDS=123456789
ENV=dev
DATABASE_PATH=data/bot.db
TSD_CONFIG=config/config.yaml
```

Jalankan aplikasi dan test:

```bash
python -m bot
pytest -v
ruff check .
ruff format --check .
```

Variabel runtime yang didukung:

| Variable | Required | Default | Description |
|---|---|---:|---|---|
| `BOT_TOKEN` | Ya | - | Token dari BotFather |
| `ADMIN_USER_IDS` | Produksi | kosong | ID admin dipisahkan koma, opsional `ID:username` |
| `OPERATOR_USER_IDS` | Tidak | kosong | ID operator (monitoring + service), format sama |
| `VIEWER_USER_IDS` | Tidak | kosong | ID viewer (read-only), format sama |
| `STRICT_USERNAME_MATCH` | Tidak | `0` | `1` = wajibkan binding username untuk semua entri whitelist |
| `LOG_CHAT_ID` | Tidak | kosong | Chat tujuan salinan audit opsional |
| `TSD_PIN` | Tidak | kosong | PIN awal aksi kritikal (4-8 digit) sebelum diatur via `/pin` |
| `PIN_TTL_SECONDS` | Tidak | `300` | Lama PIN dianggap valid; `0` = selalu minta PIN |
| `AUTH_MAX_ATTEMPTS` | Tidak | `5` | Kegagalan PIN sebelum akun terkunci |
| `AUTH_LOCKOUT_SECONDS` | Tidak | `900` | Durasi lockout |
| `RATE_LIMIT_PER_MINUTE` | Tidak | `30` | Batas pesan per user per menit |
| `ENV` | Tidak | `dev` | Nama environment |
| `DATABASE_PATH` | Tidak | `data/bot.db` | Path SQLite |
| `TSD_CONFIG` | Tidak | `config/config.yaml` | Path registry YAML |

Produksi selalu menggunakan Telegram long polling. Variabel webhook bukan bagian dari jalur deployment yang didukung.

## License

MIT License, lihat [`LICENSE`](LICENSE).
