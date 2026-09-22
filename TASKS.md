# Telegram Server Dash - Project & Task List

Bot Telegram sebagai dashboard kontrol & monitoring VPS multi-server.

- **Status:** Implementasi berjalan — fondasi (§0) dan Autentikasi & Kontrol Akses (§1) selesai di kode dengan test otomatis (164 test lulus); fitur §2–§7 masih perencanaan
- **Direktori:** `G:\Private Project\Telegram Server Dash`
- **Legenda:** `[ ]` belum, `[~]` dikerjakan, `[x]` selesai (implementasi + test otomatis, belum tentu sudah terverifikasi di host produksi), `[!]` butuh aksi/verifikasi manual di host produksi

---

## 0. Keputusan Awal & Fondasi

- [x] **Tentukan arsitektur MVP:** bot berjalan native pada satu VPS dan memonitor host yang sama melalui `transport: local`.
- [x] **Pilih tech stack:** rekomendasi Python (`aiogram`/`python-telegram-bot`) + `paramiko`/`asyncssh`; database `SQLite` (mulai) → `PostgreSQL` (skala lanjut).
- [x] **Kontrak UI bot:** wajib **Reply Keyboard saja** (tanpa Inline Keyboard), dengan tombol navigasi `Cancel` / `Back` / `Home` di setiap state — lihat §10.
- [x] **Struktur proyek:** siapkan folder `bot/`, `core/` (collector metrik), `db/`, `config/`, `handlers/`, `alerts/`, dan `plugins/`.
- [x] **Konfigurasi & secrets:** file `.env` + `config.yaml` untuk daftar server, token bot, dan kredensial; jangan hardcode.
- [x] **Fondasi deployment native:** service systemd dan `setup.sh` untuk install, update, configure, diagnostics, dan uninstall.
- [x] **CI dasar:** lint (`ruff check` + `ruff format --check`) dan unit test (`pytest`) tersedia di GitHub Actions; trigger otomatis `push`/`pull_request` dimatikan, CI dijalankan manual via `workflow_dispatch`.

### Checklist Deployment Native

- [x] Service berjalan sebagai system user khusus `tsd`, bukan root.
- [x] Aplikasi, konfigurasi, dan data memakai path FHS di `/opt`, `/etc`, dan `/var/lib`.
- [x] Token disimpan pada environment file mode `0600` di luar checkout aplikasi.
- [x] Database SQLite persisten di `/var/lib/telegram-server-dash/bot.db`.
- [x] Alur update dan uninstall mempertahankan konfigurasi serta data secara default.
- [!] Dokumentasikan dan uji prosedur backup/restore pada host produksi.
- [!] Tambahkan aturan sudoers per-command sebelum fitur manajemen privileged diaktifkan; jangan jalankan bot sebagai root.
- [!] Uji installer end-to-end pada Ubuntu dan Debian bersih.

### Deliverable
Bot echo sederhana berjalan, siap menerima handler baru, dan terhubung ke satu server uji.

---

## 1. Autentikasi & Kontrol Akses (Prasyarat Semua Fitur)

**Status: selesai** (implementasi + test, 164 test lulus, `ruff check` bersih).

Modul: `config/settings.py`, `db/schema.py`, `db/database.py`, `core/auth.py`, `core/rate_limit.py`, `core/audit.py`, `bot/services.py`, `bot/middleware.py`, `handlers/critical.py`, `handlers/admin.py`.

### Kebutuhan Teknis Bersama

| Aspek | Ketentuan |
|---|---|
| Enforcement point | Satu `AccessMiddleware` terdaftar sebagai `dp.message.outer_middleware` (lihat `bot/app.py`); seluruh handler berada di belakangnya sehingga tidak ada command yang lolos tanpa autentikasi. |
| Injeksi konteks | Middleware menyuntikkan `services`, `auth_user`, dan `role` ke `data` handler. Handler tidak lagi membaca `.env` untuk otorisasi. |
| Konfigurasi | `ADMIN_USER_IDS`, `OPERATOR_USER_IDS`, `VIEWER_USER_IDS` (entri `ID` atau `ID:username`), `STRICT_USERNAME_MATCH`, `TSD_PIN`, `PIN_TTL_SECONDS`, `AUTH_MAX_ATTEMPTS`, `AUTH_LOCKOUT_SECONDS`, `RATE_LIMIT_PER_MINUTE`. |
| Cakupan chat | Hanya private chat; update dari grup/kanal dan user bot diabaikan (`return None`). |
| Default aman | Tanpa user terdaftar semua akses ditolak (default-deny). Sebelumnya daftar admin kosong berarti *allow-all*; sekarang tidak. |
| Tabel SQLite | `users` (role, PIN hash, `is_active`, `failed_attempts`, `locked_until`, `pin_verified_until`, `last_seen`) dan `rate_limit_counters` (fixed window per user). Satu koneksi bersama, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` agar jalur auth/rate-limit/audit per pesan tidak membuka koneksi baru. |
| Redaksi rahasia | Jalur penolakan dan rate limit hanya mencatat label aman; isi pesan berbentuk PIN di-mask menjadi `<pin>` di audit trail dan alert admin (PIN tidak pernah tersimpan atau tersiar). |
| Fail-safe audit | Kegagalan tulis/mirror audit ditangkap dan di-log, tidak menggagalkan aksi user. |

- [x] **Whitelist Telegram user ID:** hanya ID terdaftar yang boleh memakai bot; tolak akses lain + notifikasi ke admin.
  - Langkah: seed/refresh whitelist saat startup (`build_services()` → `AuthService.sync_users_from_settings()`) dengan upsert ke tabel `users`; role dan `is_active=1` diperbarui, PIN serta hitungan lockout tidak ditimpa.
  - Langkah: rekonsiliasi env → DB — ID yang tidak lagi tercantum di daftar env dinonaktifkan saat sync sehingga offboarding lewat env benar-benar mencabut akses; ID yang ditambahkan kembali otomatis aktif.
  - Langkah: verifikasi **ID + username** — entri whitelist boleh ditulis `ID:username` (mis. `ADMIN_USER_IDS=123456789:namauser`); bila binding ada, pesan hanya lolos ketika ID dan username cocok (normalisasi tanpa `@`, case-insensitive). Status penolakan baru `USERNAME_MISMATCH` → balasan khusus, audit `auth.denied.username_mismatch`, dan alert admin berisi username yang dipakai pengirim.
  - Langkah: mode ketat `STRICT_USERNAME_MATCH=1` mewajibkan binding username untuk semua entri whitelist; startup gagal cepat dengan pesan perbaikan bila ada ID tanpa binding. Tanpa strict, admin tanpa binding tetap masuk tetapi dicatat sebagai warning di journal.
  - Langkah: middleware memanggil `AuthService.authenticate(user_id, username)` pada setiap pesan; status `UNKNOWN`/`INACTIVE`/`LOCKED`/`USERNAME_MISMATCH` langsung ditolak sebelum handler.
  - Teknis: notifikasi pelanggaran dikirim ke semua `ADMIN_USER_IDS` + `LOG_CHAT_ID`, dengan cooldown 10 menit per user (`ADMIN_NOTIFY_COOLDOWN_SECONDS`) supaya tidak spam.
  - Teknis: `last_seen` dan `username` diperbarui lazy (throttle 60 detik) tanpa menulis DB di setiap pesan; `/whoami` dan `/users` menampilkan status binding (`terikat @username`).
  - Teknis: parsing whitelist dari env memakai `NoDecode` + `parse_user_ids()` sehingga `ADMIN_USER_IDS=123456789` (gaya `setup.sh`) dan `1,2` sama-sama valid; sebelumnya ID tunggal diam-diam menjadi `[]` dan daftar koma membuat startup gagal.
  - Uji: `tests/test_middleware.py`, `tests/test_app_wiring.py` (dispatcher asli + sesi Telegram stub), `tests/test_config.py::TestUserIdsParsing`.

- [x] **Role-Based Access Control (RBAC):** role `admin` (semua aksi), `operator` (monitoring + service), `viewer` (hanya baca).
  - Langkah: definisikan `Role` dan `Permission` beserta matriks `ROLE_PERMISSIONS` di `core/auth.py`.
  - Teknis: permission MVP — `view_status` (viewer+), `manage_service` & `exec_command` (operator+), `critical_action`, `manage_users`, `view_audit` (admin).
  - Teknis: `has_permission()` bersifat default-deny untuk role/permission tak dikenal; role tersimpan di DB dan dapat diubah via `AuthService.set_role()` (dipakai saat UI manajemen user ditambahkan).
  - Teknis: pengguna yang ada di beberapa daftar env memakai role tertinggi (admin > operator > viewer).
  - Teknis: kebijakan per aksi fleksibel — `CriticalActionSpec.permission` dapat di-override handler §3/§4 (mis. kill proses memakai `exec_command` untuk operator, reboot/firewall tetap `critical_action` untuk admin).
  - Teknis: `/whoami` menampilkan ID, role, status PIN, status lockout, dan daftar permission aktif.
  - Uji: `tests/test_auth.py::TestRolePermissions`, `tests/test_pin_flow.py::TestWhoami`, `tests/test_app_wiring.py`.

- [x] **PIN / 2FA untuk aksi kritikal:** reboot, kill proses, hapus file, ubah firewall wajib konfirmasi PIN.
  - Langkah: implementasikan alur konfirmasi Reply Keyboard–only di `handlers/critical.py`: `request_critical_action()` → state `PinFlow.confirm_action` (tombol `✅ Ya` / `❌ Batal` + baris navigasi) → state `PinFlow.enter_pin` bila PIN belum terverifikasi.
  - Langkah: registry aksi kritikal (`register_critical_action(spec, executor)`) agar handler fitur §3/§4 cukup mendaftarkan executor-nya; eksekusi hanya dipanggil setelah PIN benar (atau TTL masih berlaku).
  - Teknis: PIN disimpan sebagai hash PBKDF2-HMAC-SHA256 (120.000 iterasi, salt acak, format `pbkdf2_sha256$iterations$salt$hash`) di kolom `users.pin_hash`; `TSD_PIN` hanya menjadi fallback awal sebelum user mengatur PIN sendiri via `/pin`.
  - Teknis: format PIN 4–8 digit angka, divalidasi di `normalize_pin()` (dipakai config, `/pin`, dan input aksi kritikal); PIN tidak pernah ditampilkan kembali atau ditulis ke log/audit (audit mencatat `<pin>`).
  - Teknis: `PIN_TTL_SECONDS` (default 300) menyimpan stempel `pin_verified_until`; `0` berarti PIN selalu diminta. Konfirmasi Ya/Batal tetap wajib bahkan saat TTL aktif.
  - Teknis: guardrail state — teks bebas saat konfirmasi dijawab `Pilih ✅ Ya atau ❌ Batal`, tombol `Cancel`/`Back`/`Home` selalu tersedia; `Cancel` maupun `Back` membatalkan konfirmasi yang sedang aktif (tidak ada aksi kritikal yang tetap "terpasang" di latar belakang).
  - Teknis: percobaan aksi kritikal tanpa permission dicatat sebagai `auth.denied.permission` di audit trail.
  - Uji: `tests/test_pin_flow.py` (setup, ganti PIN, konfirmasi, pembatalan, penolakan role viewer, guardrail, TTL).

- [x] **Rate limiting & lockout:** batas command per menit per user; lockout setelah N kali gagal auth.
  - Langkah: `core/rate_limit.py` menerapkan fixed window 60 detik per user dengan UPSERT atomik pada tabel `rate_limit_counters`; baris window lama dibersihkan otomatis.
  - Teknis: batas dari `RATE_LIMIT_PER_MINUTE` (default 30). Melebihi batas → balasan `⏳ Terlalu banyak permintaan...` berisi `retry_after`, ditulis ke audit sebagai `rate_limit.denied`, dan handler tidak dijalankan.
  - Teknis: tombol `Cancel`/`Back`/`Home` dikecualikan dari rate limit agar jalan keluar selalu tersedia (tidak ada dead-end); untuk pengirim tak dikenal, pesan di atas kuota diabaikan tanpa balasan dan tanpa entri audit tambahan agar flood tidak bisa amplifier balasan/DB.
  - Teknis: lockout via `AuthService.register_failed_attempt()` — setelah `AUTH_MAX_ATTEMPTS` (default 5) kegagalan PIN beruntun, user dikunci `AUTH_LOCKOUT_SECONDS` (default 900) dan semua pesannya ditolak dengan sisa waktu; PIN yang benar mereset hitungan.
  - Teknis: setelah masa lockout berakhir, hitungan kegagalan direset (`authenticate`/`register_failed_attempt`) sehingga user kembali mendapat kuota percobaan penuh, bukan terkunci ulang oleh sisa hitungan lama.
  - Teknis: pemulihan admin `/unlock <user_id>` (permission `manage_users`) untuk membersihkan lockout.
  - Teknis: percobaan gagal (PIN salah, akses ditolak, permission ditolak, rate limit) semuanya tercatat di audit trail; isi pesan berbentuk PIN di-redact menjadi `<pin>`.
  - Uji: `tests/test_rate_limit.py`, `tests/test_auth.py::TestLockout`, `tests/test_middleware.py`, `tests/test_admin_handlers.py::TestUnlockCommand`.

- [x] **Audit trail:** simpan log semua aksi (user, command, server, waktu, hasil) ke database + kirim copy ke channel log.
  - Langkah: `core/audit.py` menulis setiap aksi ke tabel `audit_log` (sudah ada) dan, bila `LOG_CHAT_ID` diisi, mengirim salinan berformat HTML ke channel tersebut.
  - Teknis: entri berisi `user_id`, `username`, `command`, `server_name`, `action`, `result`, `timestamp`; `action` memakai namespace `auth.*`, `critical.*`, `monitor.*`, `admin.*`, `nav.*`, `rate_limit.*`.
  - Teknis: command monitoring (`/status`, `/ping`, `/monitor`, `/cpu`, `/mem`, `/net`, `/disk`, `/proc`) menulis audit dengan command yang dipakai user (slash command atau label tombol) dan nama server pada aksi kritikal.
  - Teknis: mirror dibungkus `try/except` — kegagalan Telegram tidak pernah menggagalkan aksi; `AuditLogger.fetch_recent()` dipakai admin untuk inspeksi via `/audit [n]` (maks 25 entri).
  - Teknis: input user selalu di-escape HTML sebelum dikirim (anti-injection pada ParseMode.HTML).
  - Uji: `tests/test_audit.py`, `tests/test_admin_handlers.py::TestAuditCommand`, `tests/test_middleware.py`.

### Deliverable
Tidak ada command yang bisa dieksekusi sebelum user terautentikasi dan lolos RBAC.

Verifikasi: `pytest -q` (164 lulus) dan `ruff check .` + `ruff format --check .` bersih; alur nyata diuji lewat `Dispatcher.feed_update` dengan sesi Telegram stub di `tests/test_app_wiring.py`. Verifikasi pada host produksi menunggu item §0 (`[!]`): uji installer end-to-end dan uji backup/restore.

---

## 2. Monitoring Real-time

- [ ] **Status server:** tampilkan `uptime`, load average 1/5/15 menit, hostname, kernel, dan OS.
- [ ] **CPU monitor:** persentase pemakaian per core, 5 proses teratas, suhu CPU (`sensors`).
- [ ] **RAM & swap:** total/used/free, cache vs buffer, swap usage, 5 proses paling rakus memori.
- [ ] **Disk & I/O:** `df -h` per partisi, inode usage, `iostat`, status SMART.
- [ ] **Jaringan:** bandwidth in/out (`vnstat`), jumlah koneksi aktif (`ss -tunap`), latency `ping`, packet loss.
- [ ] **Monitor proses:** daftar proses teratas, pencarian proses, jumlah zombie, kill proses (dengan konfirmasi).
- [ ] **Grafik historis:** chart tren CPU/RAM/disk untuk rentang 1 jam / 24 jam / 7 hari (simpan sampel ke DB).
- [ ] **Auto-refresh dashboard:** pesan yang bisa di-edit berkala (mis. tiap 30 detik) alih-alih spam pesan baru.

### Metrik Acuan
`load average`, `% CPU per core`, `RAM used/total`, `disk used/total & inode`, `rx/tx bytes/detik`, `koneksi ESTABLISHED`, `zombie count`.

### Deliverable
Satu command `/status` dan `/monitor` menghasilkan dashboard live untuk server terpilih.

---

## 3. Manajemen Sistem

- [ ] **Manajemen service:** `systemctl status/start/stop/restart/enable/disable` dengan daftar unit yang diizinkan.
- [ ] **Manajemen Docker:** `docker ps -a`, start/stop/restart, lihat log, `docker stats` per container, prune.
- [ ] **Exec command aman:** whitelist command, blokir pola berbahaya, streaming output, timeout eksekusi.
- [ ] **Manajemen paket:** cek update (`apt list --upgradable`), upgrade penuh, upgrade security-only, riwayat paket.
- [ ] **File manager:** upload/download file via Telegram, hapus, rename, cek ukuran direktori (`du -sh`).
- [ ] **Log viewer:** `journalctl -u <service> -n 100`, tail log nginx/apache, filter level error.
- [ ] **Cron & task:** lihat/edit crontab, status job terakhir, trigger manual.
- [ ] **Kontrol daya:** reboot, shutdown, cancel shutdown — wajib konfirmasi ganda + PIN.
- [ ] **Manajemen user OS:** `who`, daftar user, tambah/hapus user, kelola grup, kunci akun.
- [ ] **Info hardware:** CPU model & core, RAM total, disk, GPU, `lscpu`/`lshw`.

### Deliverable
Semua operasi harian server dapat dilakukan dari chat tanpa buka terminal.

---

## 4. Keamanan

- [ ] **Firewall manager:** `ufw status/allow/deny`, lihat `iptables -L`, buka/tutup port dengan konfirmasi.
- [ ] **Fail2ban:** daftar jail aktif, IP terban, unban IP, statistik serangan per hari.
- [ ] **Deteksi login SSH:** notifikasi real-time login sukses/gagal, sertakan IP + geo-lokasi + user.
- [ ] **Port & service scan:** daftar port terbuka (`ss -tulpn`), peringatan service tak dikenal terekspos publik.
- [ ] **SSH key manager:** daftar `authorized_keys`, tambah/hapus key, peringatan key lemah/duplikat.
- [ ] **Security audit:** jalankan `lynis`/`rkhunter` terjadwal, cek permission file sensitif, laporan CVE.
- [ ] **Izin akses bot:** rutin review user terdaftar, cabut akses otomatis saat tidak aktif N hari.

### Deliverable
Notifikasi keamanan masuk otomatis dan semua perubahan firewall/akses tercatat di audit trail.

---

## 5. Otomasi & Alerting

- [ ] **Threshold alert:** notifikasi jika CPU >90%, RAM >85%, disk >80%, swap tinggi selama X menit.
- [ ] **Alert service down:** deteksi systemd unit atau proses berhenti, sertakan status dan log terakhir.
- [ ] **Alert konektivitas:** heartbeat untuk transport multi-server masa depan; notifikasi bila server tidak respons >N detik.
- [ ] **Scheduled report:** ringkasan harian/mingguan (uptime, peak resource, jumlah error, event keamanan).
- [ ] **Auto-remediation:** auto-restart service crash, auto-clear cache saat RAM kritis, auto-prune Docker.
- [ ] **Backup manager:** backup terjadwal (rsync/tar/dump DB), verifikasi integritas, kirim salinan ke cloud/Telegram.
- [ ] **Watchdog proses:** restart otomatis proses mati dengan batas retry + eskalasi jika gagal terus.
- [ ] **Deteksi anomali trafik:** alert lonjakan bandwidth, koneksi mencurigakan, indikasi DDoS.
- [ ] **Maintenance mode:** mode senyap terjadwal; tunda alert non-kritikal selama perawatan.
- [ ] **Integrasi eksternal:** relay ke Slack/Discord/email, endpoint webhook untuk CI/CD, exporter Prometheus.

### Deliverable
Bot mampu mendeteksi masalah dan (opsional) memperbaiki sendiri tanpa intervensi manual.

---

## 6. Multi-Server & UX

- [ ] **Registry server:** tambah/hapus/edit server, pengelompokan (production/staging), status online-offline agregat.
- [ ] **Switch server:** reply keyboard berisi daftar server untuk memilih server aktif; setiap command mengikuti konteks server.
- [ ] **Navigasi reply keyboard & paginasi:** menu berbasis tombol Reply Keyboard (tanpa inline), breadcrumb, halaman `Prev`/`Next` untuk daftar panjang.
- [ ] **Konfirmasi aksi berbahaya:** tombol Reply Keyboard "Ya / Batal" + PIN untuk reboot, kill, delete, firewall change.
- [ ] **Multi-bahasa (i18n):** dukungan Indonesia & Inggris.
- [ ] **Export data:** unduh statistik dalam CSV/JSON, kirim screenshot grafik.
- [ ] **Transport multi-server:** evaluasi SSH langsung atau agent ringan terenkripsi setelah MVP single-host stabil.

### Deliverable
Satu bot dapat mengelola banyak VPS dengan pengalaman chat yang konsisten.

---

## 7. Backlog / Nice-to-Have

- [ ] Integrasi monitoring eksternal (Uptime Kuma, Netdata, Grafana snapshot).
- [ ] Auto-scaling atau provisioning VPS baru via API provider.
- [ ] Prediksi kapasitas (estimasi kapan disk penuh berdasarkan tren).
- [ ] Mode offline queue: command ditunda saat server down lalu dijalankan saat pulih.
- [ ] Dukungan plugin pihak ketiga dengan sandbox permission.
- [ ] Web dashboard pendamping yang berbagi database yang sama.

---

## 8. Prioritas MVP (Rilis Pertama)

Fokus hanya pada 6 hal ini agar cepat jalan:

1. [x] Autentikasi user ID + RBAC dasar (selesai; lihat §1).
2. [ ] `/status` — CPU, RAM, disk, uptime, load.
3. [ ] Manajemen service systemd (status/start/stop/restart).
4. [ ] Exec command dengan whitelist.
5. [ ] Alert threshold dasar (CPU/RAM/disk) + service down.
6. [x] Audit trail aksi user (selesai; lihat §1).

**Kriteria rilis MVP:** admin bisa memantau dan mengendalikan satu VPS penuh dari Telegram dengan aman, dan menerima alert saat resource kritis.

> Catatan: bot MVP dibangun dengan Python + **aiogram** dan hanya memakai **Reply Keyboard** (lihat §10).

---

## 9. Urutan Pengerjaan Disarankan

| Fase | Fokus | Estimasi Relatif |
|---|---|---|
| Fase 0 | Fondasi, config, koneksi server | Kecil |
| Fase 1 | Auth + RBAC + audit trail | Kecil |
| Fase 2 | Monitoring real-time + `/status` | Sedang |
| Fase 3 | Manajemen sistem (service, docker, exec) | Sedang |
| Fase 4 | Keamanan (firewall, fail2ban, login alert) | Sedang |
| Fase 5 | Otomasi & alerting lanjutan | Besar |
| Fase 6 | Multi-server + UX polish | Besar |

---

## 10. Implementasi Bot aiogram — Kontrak UX & Navigasi

Task pengembangan bot Telegram dengan **Python + `aiogram`** yang menjadi fondasi seluruh handler. Semua fitur di §1–§7 harus mengikuti kontrak UX di bawah ini.

- [x] **Bootstrap aiogram:** set up `Dispatcher` + `Bot` dengan long polling, integrasi `config.yaml`/`.env`, inisialisasi database, serta registrasi router per modul (`handlers/`).
- [ ] **Reply Keyboard only:** semua interaksi memakai `ReplyKeyboardMarkup`; **dilarang memakai `InlineKeyboardMarkup`** — termasuk untuk menu, konfirmasi, pemilihan server, dan paginasi.
- [ ] **Tombol navigasi wajib:** setiap state/page menyertakan tiga tombol tetap — `Cancel` (batalkan proses berjalan ke konteks aman), `Back` (kembali ke state sebelumnya via riwayat navigasi, bukan sekadar root), dan `Home` (langsung ke menu utama + reset konteks).
- [ ] **State machine terpusat:** kelola alur dengan `aiogram` FSM (`StatesGroup` + `MemoryStorage`/Redis) sehingga transisi state konsisten dan bisa dibatalkan dari mana saja.
- [ ] **Manajemen konteks:** simpan konteks aktif per user (server terpilih, menu, breadcrumb) agar `Back`/`Cancel`/`Home` berperilaku benar.
- [ ] **Stack navigasi:** riwayat menu (push/pop) supaya `Back` menelusuri jalur yang benar, dengan perilaku aman saat riwayat kosong.
- [ ] **Pembersihan keyboard:** hapus Reply Keyboard yang menggantung (`ReplyKeyboardRemove`) saat `Home`/`Cancel`, dan cegah tombol lama tetap terkirim sebagai input.
- [ ] **Konsistensi UX:** label tombol ringkas dan konsisten, pesan konfirmasi jelas, tidak ada dead-end — setiap layar punya jalan keluar.
- [ ] **Pesan yang bisa di-edit:** gunakan satu pesan dashboard yang di-edit berkala (`edit_text` di message id yang sama), bukan spam pesan baru.
- [ ] **Guardrail input:** validasi input teks user saat FSM menunggu nilai (mis. nama service, path file) dan tangani tombol navigasi di setiap state.
- [ ] **Error boundary:** handler error global yang mengembalikan user ke `Home` dengan pesan ramah, plus logging ke audit trail.
- [ ] **Test alur:** unit test untuk transisi state dan tombol navigasi (Cancel/Back/Home) memakai mock update aiogram.

### Aturan Navigasi

| Tombol | Perilaku |
|---|---|
| `Home` | Kembali ke menu utama, reset konteks & riwayat, tampilkan keyboard root. |
| `Back` | Kembali satu langkah ke state sebelumnya; jika di root, tidak melakukan apa-apa (atau info singkat). |
| `Cancel` | Batalkan proses berjalan (mis. eksekusi command), bersihkan konteks sementara, kembali ke state aman. |

### Deliverable

Bot aiogram berjalan dengan navigasi Reply Keyboard yang konsisten — setiap layar punya tombol `Cancel`, `Back`, dan `Home` — tanpa satu pun Inline Keyboard, dan alur state teruji otomatis.

### Kriteria Selesai

1. Tidak ada penggunaan `InlineKeyboardMarkup` di seluruh codebase.
2. Setiap handler/state menampilkan tombol `Cancel`, `Back`, `Home`.
3. `Back` mengikuti riwayat navigasi; `Home` dan `Cancel` selalu menyediakan jalan keluar.
4. Test transisi state dan navigasi lulus saat CI dijalankan manual (`gh workflow run CI`).
