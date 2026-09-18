# Telegram Server Dash

Bot Telegram sebagai dashboard kontrol & monitoring VPS multi-server.

[![CI](https://github.com/baaaaan1/telegram-server-dash/actions/workflows/ci.yml/badge.svg)](https://github.com/baaaaan1/telegram-server-dash/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Overview

Telegram Server Dash (TSD) adalah bot Telegram yang berfungsi sebagai dashboard kontrol dan monitoring untuk beberapa server VPS. Bot ini memungkinkan pengguna untuk:

- **Monitoring Real-time**: Memantau status CPU, RAM, disk, jaringan, dan layanan sistem
- **Manajemen Sistem**: Mengelola layanan systemd, Docker, file, dan proses
- **Keamanan**: Mengelola firewall, Fail2ban, dan mendeteksi login SSH
- **Otomasi**: Mengatur threshold alert dan auto-remediation

### Fitur Utama

- ✅ **Reply Keyboard Only**: Semua navigasi menggunakan Reply Keyboard tanpaInline Keyboard
- ✅ **Multi-Server**: Dapat mengelola beberapa VPS dari satu bot
- ✅ **Real-time Monitoring**: Dashboard status server langsung dari chat Telegram
- ✅ **Akun & Otorisasi**: Whitelist user ID dengan Role-Based Access Control (RBAC)
- ✅ **Database Terpadu**: SQLite untuk audit log dan metrik

## Prerequisites

- Python 3.11+ atau Docker/Docker Compose
- Bot Telegram dengan token yang valid ( dapatkan dari @BotFather di Telegram )
- Server target dengan akses SSH (opsional untuk monitoring).

## Installation Options

Ada dua cara untuk menginstal dan menjalankan TSD Bot:

### Option 1: Running Locally with Python

1. **Clone repository**:

```bash
git clone https://github.com/baaaaan1/telegram-server-dash.git
cd telegram-server-dash
```

2. **Create virtual environment**:

```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
```

3. **Install dependencies**:

```bash
pip install -r requirements.txt
```

4. **Configure environment**:

```bash
cp .env.example .env
```

5. **Edit `.env`**:

```env
BOT_TOKEN=your:bot:token:here
ADMIN_USER_IDS=123456789
ENV=dev
DATABASE_PATH=data/bot.db
```

6. **Configure servers**:

Edit `config/config.yaml` untuk menambahkan server yang ingin dimonitor:

```yaml
servers:
  - name: my-server
    group: production
    description: "Production VPS"
    transport: ssh
    host: 192.168.1.100
    port: 22
    user: ubuntu
    auth: key
    key_path: "~/.ssh/id_rsa"
```

7. **Run the bot**:

```bash
python -m telegram-server-dash
```

### Option 2: Running with Docker Compose (Recommended)

1. **Clone repository**:

```bash
git clone https://github.com/baaaaan1/telegram-server-dash.git
cd telegram-server-dash
```

2. **Configure environment**:

```bash
cp .env.example .env
```

3. **Edit `.env`**:

```env
BOT_TOKEN=your:bot:token:here
ADMIN_USER_IDS=123456789
ENV=production
DATABASE_PATH=/app/data/bot.db
```

4. **Build and start**:

```bash
docker compose up -d
```

Untuk deployment dengan **Dokploy**, lihat bagian [Dokploy Deployment](#deploy-menggunakan-dokploy) di bawah.

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `BOT_TOKEN` | Bot token dari @BotFather | Ya | - |
| `ADMIN_USER_IDS` | Daftar user ID admin (koma dipisah) | Tidak | - |
| `LOG_CHAT_ID` | Chat ID untuk log otomatis | Tidak | - |
| `ENV` | Lingkungan (dev/staging/production) | Tidak | `dev` |
| `DATABASE_PATH` | Path file database SQLite | Tidak | `data/bot.db` |
| `TSD_CONFIG` | Path ke file konfigurasi YAML | Tidak | `config/config.yaml` |
| `WEBHOOK_BASE_URL` | Base URL untuk webhook mode | Tidak | - |
| `WEBHOOK_PATH` | Path endpoint webhook | Tidak | `/webhook` |
| `WEBHOOK_SECRET_TOKEN` | Secret token untuk webhook | Tidak | - |

## API & Commands

### Command Utama

| Command | Deskripsi |
|---------|-----------|
| `/start` | Memulai bot dan menampilkan menu utama |
| `/status` | Menampilkan status server yang dikonfigurasi |
| `/ping` | Menguji konektivitas ke server |
| `/echo` | Fitur echo sederhana untuk pengujian |
| `/help` | Menampilkan panduan penggunaan |
| `Home` | Kembali ke menu utama |
| `Back` | Kembali ke layar sebelumnya |
| `Cancel` | Membatalkan operasi berjalan |

## Project Structure

```
telegram-server-dash/
├── bot/                    # Bot application
│   ├── __init__.py        # Package exports
│   ├── __main__.py        # Entry point (python -m bot)
│   ├── app.py             # Bot bootstrap and dispatcher
│   ├── keyboards.py       # Reply Keyboard builders
│   ├── nav.py             # Navigation state machine
│   └── texts.py           # Message templates
├── core/                   # Core functionality
│   ├── __init__.py
│   ├── ssh.py             # SSH connection management
│   └── probe.py           # Server probes (ping, uptime, load)
├── db/                     # Database
│   ├── __init__.py
│   ├── database.py        # SQLite wrapper
│   └── schema.py          # SQL schema
├── config/                 # Configuration
│   ├── __init__.py
│   ├── settings.py        # Pydantic Settings models
│   ├── servers.py         # Server registry from YAML
│   └── config.yaml        # Server configurations
├── handlers/               # Aiogram routers
│   ├── __init__.py
│   ├── common.py          # /start, /help, nav buttons
│   ├── status.py          # /status handler
│   ├── echo.py            # /echo handler
│   ├── navigation.py      # Navigation button router
│   └── webhook.py         # Webhook placeholder
├── alerts/                 # Alert system
├── plugins/                # Plugin sandbox
├── tests/                  # Unit tests
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=bot --cov=core --cov=config --cov=db
```

## Docker Compose

### Standard Deployment

```bash
# Build and start the bot
docker compose up -d

# View logs
docker compose logs -f

# Stop and remove containers
docker compose down

# Rebuild
docker compose up -d --build --force-recreate
```

### Docker Compose Configuration

| Service | Description |
|---------|-------------|
| `bot` | Main bot service (default) |
| `agent` | Agent daemon (optional profile) |

## Deploy Menggunakan Dokploy <a id="deploy-menggunakan-dokploy"></a>

Dokploy menyediakan antarmuka yang mudah untuk meng-deploy aplikasi Docker Compose Anda. Berikut langkah-langkahnya:

### Langkah 1: Persiapkan File

Pastikan Anda memiliki file berikut di repository Git Anda:

- `docker-compose.yml`
- `.env.example` (opsional, untuk dokumentasi variabel)

### Langkah 2: Buat Application Baru di Dokploy

1. Masuk keDasbor Dokploy Anda

2. Klik **Create Application** dan pilih **Docker Compose**

3. Pilih sumber kode:
   - **Git Source**: Hubungkan repository GitHub/Gitea/GitLab Anda
   - **Branch**: Pilih branch yang diinginkan (biasanya `main`)

### Langkah 3: Konfigurasi Environment Variables

Di tab **Environment**, tambahkan variabel-variabel berikut:

| Variable | Value | Description |
|----------|-------|-------------|
| `BOT_TOKEN` | `[your bot token]` | Bot token dari @BotFather |
| `ADMIN_USER_IDS` | `[user_id]` | ID Telegram admin |
| `ENV` | `production` | Lingkungan operasional |

> **Catatan**: Anda dapat menggunakan **Secrets Providers** untuk menyimpan `BOT_TOKEN` secara lebih aman.

### Langkah 4: Volume Konfigurasi

Untuk persistensi data, konfigurasikan volumes:

**Database Volume** (Recommended untuk produksi):

```yaml
volumes:
  - bot-data:/app/data
volumes:
  bot-data:
```

**Atau gunakan bind mount** untuk akses langsung:

```yaml
volumes:
  - "../files/bot-data:/app/data"
```

### Langkah 5: Domain & Routing (Opsional)

Jika Anda memerlukan akses web:

1. Tab **Domains** → Tambahkan domain
2. Konfigurasi SSL dengan Let's Encrypt otomatis

### Langkah 6: Deploy

1. Klik **Deploy** untuk pertama kalinya
2. Dokploy akan membangun dan menjalankan kontainer
3. Pantau status di tab **Deployments**

### Monitoring & Logs

Setelah deployment:

- **Logs**: Lihat log real-time di tab **Logs**
- **Monitoring**: Akses statistik kontainer di tab **Monitoring**
- **Backups**: Konfigurasikan backup volume di tab **Backups** (hanya untuk named volumes)

### Update Aplikasi

Setiap kali Anda melakukan push ke repository:

1. Dokploy akan mendeteksi perubahan
2. Deployment otomatis dimulai
3. Aplikasi diperbarui tanpa downtime

### Troubleshooting

**Bot tidak merespon**:
- Pastikan `BOT_TOKEN` benar di environment variables
- Cek log di tab **Logs**

**Database tidak persisten**:
- Pastikan volume sudah dikonfigurasi
- Untuk Dokploy, gunakan **named volumes** bukan bind mounts

**Error SSH koneksi ke server**:
- Pastikan server ada di `config/config.yaml`
- Periksa kredensial SSH di `key_path` atau `password_env`

## Security Considerations

- **Jangan commit `.env`** ke repository
- Gunakan environment variables yang dimanajemen Dokploy
- Bot token harus disimpan sebagai secret
- SSH keys harus didistribusikan dengan aman

## Roadmap

- [ ] Integrasi monitoring eksternal (Uptime Kuma, Netdata)
- [ ] Auto-scaling VPS
- [ ] Prediksi kapasitas
- [ ] Mode offline queue

## Contributing

1. Fork repository
2. Buat feature branch (`git checkout -b feature/aman`)
3. Commit perubahan (`git commit -m 'Tambah fitur baru'`)
4. Push branch (`git push origin feature/aman`)
5. Buka Pull Request

## License

MIT License - lihat file [LICENSE](LICENSE) untuk detail.

## Credits

- Bot dibangun dengan [aiogram](https://docs.aiogram.dev/)
- Dashboard Telegram modern dan responsif
- Dokumentasi deployment untuk [Dokploy](https://dokploy.com)