# SCELE Assignments Checker

Bot Python sederhana untuk mengambil tugas dari kalender SCELE UI dan menampilkannya di Discord melalui GitHub Actions. Setelah diaktifkan, bot mempertahankan dua pesan Discord yang sama dan mengeditnya secara berkala—bukan membuat pesan baru terus-menerus.

- 📚 **JADWAL TUGAS** — seluruh tugas yang belum lewat, diurutkan berdasarkan deadline.
- 🚨 **DEADLINE HARI INI** — tugas yang deadline-nya hari ini (WIB).

## Yang dibutuhkan

- Repository GitHub (fork repo ini bila ingin memakai versi sendiri).
- Akun SCELE yang dapat melihat kalender.
- Discord webhook untuk channel tujuan.
- GitHub Actions yang diizinkan menulis ke repository.
- Akun [cron-job.org](https://cron-job.org) untuk pemicu otomatis yang tepat waktu.

## Mulai cepat

1. Fork atau clone repository ini ke akun GitHub Anda.
2. Tambahkan tiga repository secret melalui **Settings → Secrets and variables → Actions → New repository secret**:

   | Secret | Isi |
   | --- | --- |
   | `SCELE_USERNAME` | Username SCELE Anda |
   | `SCELE_PASSWORD` | Password SCELE Anda |
   | `DISCORD_WEBHOOK_URL` | URL Discord webhook channel tujuan |

3. Pastikan **Settings → Actions → General → Workflow permissions** mengizinkan **Read and write permissions**. Bot perlu menyimpan ID pesan Discord di `state.json`.
4. Buka tab **Actions**, pilih workflow **SCELE Assignments Checker**, lalu klik **Run workflow** dengan `activate: ON`.

Activation pertama membuat dua pesan Discord dan menyimpan ID-nya. Jika activation gagal, bot tetap nonaktif. Menjalankan activation lagi saat bot sudah aktif tidak akan membuat pesan duplikat.

## Jadwal otomatis

Pemicu jadwal menggunakan cron-job.org dengan timezone `Asia/Jakarta` (WIB), lalu menjalankan workflow GitHub dengan `update_kind: BOTH`.

| WIB | Pesan yang diperbarui |
| --- | --- |
| 00.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |
| 04.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |
| 08.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |
| 12.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |
| 16.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |
| 20.00 | 📚 JADWAL TUGAS dan 🚨 DEADLINE HARI INI |

Untuk setup cron-job.org, gunakan endpoint `workflow_dispatch` GitHub dengan input `activate: OFF` dan `update_kind: BOTH`. Semua run mengedit pesan persistent yang sama, jadi tidak membuat pesan Discord tambahan. Jika salah satu pesan bot dihapus, bot membuat pengganti pada update berikutnya dan memperbarui `state.json`.

GitHub Actions dipakai untuk menjalankan bot, bukan sebagai clock. Pemicu jadwal dipindahkan ke cron-job.org karena scheduled workflow GitHub dapat terlambat atau terlewat.

### Setup cron-job.org

1. Buat fine-grained GitHub token melalui **Settings → Developer settings → Personal access tokens → Fine-grained tokens**. Batasi token hanya ke repository ini, beri izin `Actions: Read and write`, dan gunakan masa berlaku terbatas.
2. Di cron-job.org, buat satu job dengan konfigurasi berikut:

   | Field | Value |
   | --- | --- |
   | Title | `SICeKer Automatic Update` |
   | URL | `https://api.github.com/repos/OWNER/REPOSITORY/actions/workflows/notifier.yml/dispatches` |
   | Method | `POST` |
   | Timezone | `Asia/Jakarta` |
   | Crontab | `0 0,4,8,12,16,20 * * *` |
   | Save responses | Off |

   Ganti `OWNER/REPOSITORY` dengan repository Anda. Untuk repo ini, URL-nya adalah `https://api.github.com/repos/zalfredz/SICeKer/actions/workflows/notifier.yml/dispatches`.

3. Tambahkan request headers sebagai key/value:

   | Key | Value |
   | --- | --- |
   | `Accept` | `application/vnd.github+json` |
   | `Content-Type` | `application/json` |
   | `Authorization` | `Bearer TOKEN_GITHUB_KAMU` |
   | `X-GitHub-Api-Version` | `2026-03-10` |

4. Isi request body:

   ```json
   {
     "ref": "main",
     "inputs": {
       "activate": "OFF",
       "update_kind": "BOTH"
     }
   }
   ```

Jangan taruh token GitHub di repository, `.env`, GitHub Secrets, atau screenshot. Token hanya disimpan sebagai header pada job cron-job.org. Setelah membuat job, lakukan test run dan pastikan GitHub Actions menunjukkan event `workflow_dispatch` serta pesan Discord memperbarui `Last update`.

### Memilih pesan yang diperbarui

Code tetap memisahkan pembaruan pesan jadwal dan deadline. Ubah nilai `update_kind` pada request body cron-job.org sesuai kebutuhan:

| Nilai | Pesan yang diperbarui |
| --- | --- |
| `BOTH` | 📚 Jadwal tugas dan 🚨 deadline hari ini |
| `SCHEDULE` | Hanya 📚 jadwal tugas |
| `DEADLINE` | Hanya 🚨 deadline hari ini |

Untuk jadwal berbeda, buat cron job terpisah dengan `update_kind` yang sesuai. Konfigurasi bawaan repository ini memakai `BOTH` setiap empat jam.

## Yang aman diubah

| Kebutuhan | File | Yang diubah |
| --- | --- | --- |
| Nama bot Discord | `bot/notifier.py` | Nilai `BOT_USERNAME` |
| Menyembunyikan mata kuliah tertentu | `bot/main.py` | Set `UN_NOTIF` |
| Waktu update | cron-job.org | Jadwal external trigger dalam `Asia/Jakarta` |
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

## Menjalankan manual

Pada tab **Actions → SCELE Assignments Checker → Run workflow**, tersedia dua mode:

- `activate: ON` — hanya untuk mengaktifkan bot pertama kali dan membuat dua pesan persistent.
- `update_kind: BOTH`, `SCHEDULE`, atau `DEADLINE` — mengedit pesan yang dipilih memakai data SCELE terbaru.

Untuk memperbarui dua pesan persistent kapan saja, jalankan workflow dengan `update_kind: BOTH` dan `activate: OFF`. Mode ini memakai data SCELE terbaru dan mengedit pesan yang ada.

Pilih `activate` atau satu nilai `update_kind` pada setiap manual run. `update_kind` membutuhkan bot yang sudah aktif; pesan baru hanya dibuat bila bot sedang memulihkan pesan persistent yang sebelumnya dihapus.

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
ACTIVATE=OFF
UPDATE_KIND=OFF
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
