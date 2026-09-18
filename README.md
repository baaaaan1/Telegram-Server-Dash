# Telegram Server Dash

Telegram Server Dash (TSD) adalah bot Telegram berbasis aiogram untuk monitoring VPS. MVP saat ini ditujukan untuk satu host: bot berjalan langsung sebagai service systemd dan `transport: local` membaca informasi VPS melalui utilitas Linux dan `/proc`.

[![CI](https://github.com/baaaaan1/telegram-server-dash/actions/workflows/ci.yml/badge.svg)](https://github.com/baaaaan1/telegram-server-dash/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Status Proyek

Fondasi bot, navigasi, registry server, probe, SQLite, dan deployment native telah tersedia. Monitoring lengkap, RBAC, alerting, dan operasi manajemen privileged masih berada dalam roadmap. Lihat [`TASKS.md`](TASKS.md) untuk status yang lebih rinci.

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
|---|---:|---|---|
| `BOT_TOKEN` | Ya | - | Token dari BotFather |
| `ADMIN_USER_IDS` | Produksi | kosong | ID admin dipisahkan koma |
| `LOG_CHAT_ID` | Tidak | kosong | Chat tujuan log opsional |
| `ENV` | Tidak | `dev` | Nama environment |
| `DATABASE_PATH` | Tidak | `data/bot.db` | Path SQLite |
| `TSD_CONFIG` | Tidak | `config/config.yaml` | Path registry YAML |

Produksi selalu menggunakan Telegram long polling. Variabel webhook bukan bagian dari jalur deployment yang didukung.

## License

MIT License, lihat [`LICENSE`](LICENSE).
