# SCELE Assignments Checker

Bot Python sederhana untuk mengambil tugas dari kalender SCELE UI dan menampilkannya di Discord melalui GitHub Actions. Setelah diaktifkan, bot mempertahankan dua pesan Discord yang sama dan mengeditnya secara berkala—bukan membuat pesan baru terus-menerus.

- 📚 **JADWAL TUGAS** — seluruh tugas yang belum lewat, diurutkan berdasarkan deadline.
- 🚨 **DEADLINE HARI INI** — tugas yang deadline-nya hari ini (WIB).

## Yang dibutuhkan

- Repository GitHub (fork repo ini bila ingin memakai versi sendiri).
- Akun SCELE yang dapat melihat kalender.
- Discord webhook untuk channel tujuan.
- GitHub Actions yang diizinkan menulis ke repository.

## Mulai cepat

1. Fork atau clone repository ini ke akun GitHub Anda.
2. Tambahkan tiga repository secret melalui **Settings → Secrets and variables → Actions → New repository secret**:

   | Secret | Isi |
   | --- | --- |
   | `SCELE_USERNAME` | Username SCELE Anda |
   | `SCELE_PASSWORD` | Password SCELE Anda |
   | `DISCORD_WEBHOOK_URL` | URL Discord webhook channel tujuan |

3. Pastikan **Settings → Actions → General → Workflow permissions** mengizinkan **Read and write permissions**. Bot perlu menyimpan ID pesan Discord di `state.json`.
4. Buka tab **Actions**, pilih workflow **SCELE Assignments Checker**, lalu klik **Run workflow** dengan `activate: ON` dan `tester: OFF`.

Activation pertama membuat dua pesan Discord dan menyimpan ID-nya. Jika activation gagal, bot tetap nonaktif. Menjalankan activation lagi saat bot sudah aktif tidak akan membuat pesan duplikat.

## Jadwal otomatis

Semua deadline dan logika tanggal menggunakan timezone `Asia/Jakarta` (WIB).

| WIB | Pesan yang diperbarui |
| --- | --- |
| 00.07, 00.22, 00.37, 00.52 | 📚 JADWAL TUGAS |
| 10.07, 10.22, 10.37, 10.52 | 🚨 DEADLINE HARI INI |
| 12.07, 12.22, 12.37, 12.52 | 📚 JADWAL TUGAS |

Setiap slot memiliki beberapa retry agar GitHub scheduler yang terlambat atau melewatkan satu trigger tidak menghentikan automation. Semua retry hanya mengedit pesan persistent yang sama, jadi tidak membuat pesan Discord tambahan. Jika salah satu pesan bot dihapus, bot membuat pengganti pada update berikutnya dan memperbarui `state.json`.

## Yang aman diubah

| Kebutuhan | File | Yang diubah |
| --- | --- | --- |
| Nama bot Discord | `bot/notifier.py` | Nilai `BOT_USERNAME` |
| Menyembunyikan mata kuliah tertentu | `bot/main.py` | Set `UN_NOTIF` |
| Waktu workflow | `.github/workflows/notifier.yml` dan `bot/main.py` | Cron workflow **dan** `scheduled_update_kind()` |
| Credential saat menjalankan lokal | `.env` | Isi environment variable, jangan commit file ini |

### Menyembunyikan mata kuliah

Tambahkan nama mata kuliah ke `UN_NOTIF` di `bot/main.py` apabila kalender Anda juga menampilkan kelas yang tidak ingin dinotifikasi, misalnya kelas asdos:

```python
UN_NOTIF = {
    "Kalkulus 1 (A,B,C,D,E,F,G,H) Gasal 2026/2027",
    "Nama mata kuliah lain",
}
```

Tulis nama seperti yang tampil di Discord. Prefix administratif seperti `[Reg]` dan `[SI.Reg]` sudah dihapus parser sebelum perbandingan dilakukan.

### Mengubah jadwal

GitHub Actions memakai UTC dan scheduler bersama dapat terlambat atau melewatkan trigger. Karena itu setiap update memiliki retry pada menit `07`, `22`, `37`, dan `52`. Bila waktu workflow diubah di `.github/workflows/notifier.yml`, sesuaikan juga map `SCHEDULE_UPDATE_KINDS` di `bot/main.py`; map tersebut menentukan apakah cron tersebut memperbarui jadwal atau deadline hari ini.

## Menjalankan manual

Pada tab **Actions → SCELE Assignments Checker → Run workflow**, tersedia tiga mode:

- `activate: ON` — hanya untuk mengaktifkan bot pertama kali dan membuat dua pesan persistent.
- `tester: ON` — mengirim preview dengan data SCELE asli dan format produksi, tetapi tidak mengubah `state.json` atau jadwal production.
- `update_now: ON` — langsung mengedit dua pesan persistent memakai data SCELE terbaru.

Untuk memperbarui dua pesan persistent kapan saja, jalankan workflow dengan `update_now: ON` dan mode lain tetap `OFF`. Mode ini memakai data SCELE terbaru, mengedit pesan yang ada, dan tidak membuat preview atau activation baru.

Pilih hanya satu mode pada setiap manual run. `update_now` membutuhkan bot yang sudah aktif; pesan baru hanya dibuat bila bot sedang memulihkan pesan persistent yang sebelumnya dihapus.

## Menjalankan lokal

Butuh Python 3.11 atau lebih baru.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Isi `.env`:

```env
SCELE_USERNAME=username_scele
SCELE_PASSWORD=password_scele
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TESTER=OFF
ACTIVATE=OFF
MANUAL_UPDATE=OFF
```

Lalu jalankan:

```powershell
python -m bot.main
pytest
```

`.env` berisi credential dan sudah diabaikan Git. Jangan pernah commit atau membagikannya.

## Cara kerja singkat

Parser membaca semua event kalender yang mempunyai `data-event-id`, mengambil deadline, course, dan link aktivitas. Prefix course `[Reg]` / `[SI.Reg]` serta akhiran judul seperti `is due` dibersihkan untuk tampilan. Event tanpa deadline atau yang sudah lewat tidak masuk jadwal. Description hanya dipakai internal untuk membantu membaca deadline; tidak pernah ditampilkan ke Discord.

`state.json` harus tetap berada di repository karena menyimpan status aktif dan ID dua pesan Discord. Workflow hanya membuat commit state saat nilai tersebut benar-benar berubah.

## Keterbatasan

Login saat ini menggunakan form login Moodle dengan username, password, dan `logintoken`. Jika SCELE suatu saat mewajibkan CAPTCHA, MFA interaktif, SSO khusus, atau memblokir runner GitHub, GitHub Secrets saja tidak cukup. Gunakan jalur akses resmi yang diizinkan pengelola SCELE; jangan menyimpan cookie atau token sesi jangka panjang di repository.
