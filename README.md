# SCELE Assignments Checker

Bot Python untuk mengambil upcoming assignment SCELE UI dan mengirimkannya ke Discord melalui webhook. Semua deadline diproses dengan timezone `Asia/Jakarta` (WIB).

## Cara kerja

1. Bot membuka kalender upcoming SCELE menggunakan satu HTTP session.
2. Jika SCELE meminta login, bot menjalankan form login Moodle dengan `logintoken` dan credential dari environment variable.
3. Parser memakai `data-event-id` sebagai ID unik, mengambil course/activity URL, dan memprioritaskan deadline lengkap pada description. Prefix `[SI.Reg]`/`[Reg]` serta akhiran `is due` dihapus untuk tampilan Discord.
4. Event tanpa deadline maupun deadline yang sudah lewat tidak masuk jadwal.
5. Pada setiap jadwal tetap, bot mengirim satu message **JADWAL TUGAS**, diurutkan dari deadline terdekat.
6. Sesudahnya, setiap assignment yang deadline-nya hari itu menerima satu message **DEADLINE HARI INI**. Informasi description selain baris deadline ditampilkan hanya bila ada.

## Jadwal GitHub Actions

Workflow memakai UTC karena GitHub Actions tidak memakai WIB:

| Cron UTC | Waktu WIB | Notifikasi |
| --- | --- | --- |
| `0 5 * * *` | 12.00 WIB | JADWAL TUGAS, lalu deadline hari ini |
| `0 17 * * *` | 00.00 WIB hari berikutnya | JADWAL TUGAS, lalu deadline hari ini |

Workflow juga dapat dijalankan melalui **Actions → SCELE Discord Notifier → Run workflow**.

## Tester mode

Konfigurasi sederhana memakai `TESTER=ON` atau `TESTER=OFF`.

- `OFF` adalah production: hanya run terjadwal pada 12.00 dan 00.00 WIB yang mengirim serta memperbarui `state.json`.
- `ON` adalah test: jalankan workflow manual, pilih input **tester: ON**, lalu bot segera mengambil data SCELE asli dan mengirim embed dengan format production.

Tester mengirim schedule terlebih dahulu, kemudian satu embed deadline hari ini untuk setiap tugas yang benar-benar jatuh tempo hari itu. Tester tidak menulis `schedule_last_sent`, tidak menandai `deadline_today_sent`, dan tidak mengubah jadwal production berikutnya. Untuk test lokal, tambahkan `TESTER=ON` di `.env`; sesudah selesai, ubah kembali ke `TESTER=OFF`.

## Menjalankan lokal

Butuh Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Isi file `.env` lokal:

```env
SCELE_USERNAME=username_scele
SCELE_PASSWORD=password_scele
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_AVATAR_URL=https://example.com/foto-profil.png
TESTER=OFF
```

Lalu jalankan:

```powershell
python -m bot.main
pytest
```

`.env` diabaikan Git dan tidak boleh di-commit. `.env.example` adalah template aman. Environment variable yang sudah ada selalu diprioritaskan daripada nilai `.env`.

## GitHub Secrets

Buka **Settings → Secrets and variables → Actions**, kemudian buat secrets berikut:

| Secret | Isi |
| --- | --- |
| `SCELE_USERNAME` | Username SCELE |
| `SCELE_PASSWORD` | Password SCELE |
| `DISCORD_WEBHOOK_URL` | URL Discord webhook |
| `DISCORD_AVATAR_URL` | URL foto profil bot (opsional) |

Buat webhook lewat **Discord channel → Edit Channel → Integrations → Webhooks → New Webhook**. URL webhook adalah rahasia dan tidak pernah dicetak oleh bot.

Workflow meng-commit `state.json` setelah pengiriman yang berhasil. Berikan `GITHUB_TOKEN` permission **Read and write permissions** agar state bertahan di runner GitHub Actions berikutnya. State menyimpan slot jadwal terakhir (`00.00` atau `12.00 WIB`) dan tanggal notifikasi deadline per `event_id`, sehingga retry tidak mengirim duplikat.

## Format pesan

Setiap webhook menggunakan username `ALz SceleReminder`. Jika `DISCORD_AVATAR_URL` tersedia, foto tersebut juga digunakan sebagai avatar webhook. Satu schedule menggunakan satu Discord Embed biru (`3447003`) dan setiap tugas menjadi satu field:

```text
📚 JADWAL TUGAS

🎓 Nama Mata Kuliah
**Tugas 0**
⏰ Deadline: **Senin, 7 September 2026, Pukul 23.55**
[🔗 Buka Tugas](https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440)
```

Deadline hari ini menggunakan satu embed merah (`15158332`) berjudul `🚨 DEADLINE HARI INI`, dengan footer pengingat. Description plain-text hanya ditampilkan sebagai `📝 Informasi Tugas` jika berisi informasi selain deadline. Satu schedule dijaga sebagai satu embed/message; Discord membatasi satu embed pada 25 fields, sehingga run akan gagal jelas bila tugas melebihi batas tersebut agar tidak ada tugas yang diam-diam hilang.

## Testing

Fixture lokal di `tests/fixtures/upcoming_calendar.html` tidak memerlukan login atau network. Test mencakup multi-event parsing, course URL, normalisasi title/course, deadline WIB, pengurutan, filter deadline hari ini/event lewat, format payload tanpa mengirim webhook, dan state anti-duplikasi.

```powershell
pytest
```

## Authentication dan keterbatasan

Pemeriksaan terhadap URL kalender menunjukkan halaman tersebut mengarah ke form login Moodle dengan `logintoken`, `username`, dan `password`; alur ini didukung lewat Secrets tanpa menyimpan cookie atau token. Bila SCELE kelak mewajibkan CAPTCHA, MFA interaktif, SSO yang tidak dapat diselesaikan dengan form login, atau membatasi IP GitHub-hosted runner, autentikasi otomatis tidak akan kompatibel. Gunakan self-hosted runner yang diizinkan atau akses/API resmi dari pengelola SCELE; jangan menyimpan cookie jangka panjang di repository.
