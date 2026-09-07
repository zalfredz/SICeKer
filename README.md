# SCELE Assignments Checker

Bot scheduled GitHub Actions yang mengambil assignment upcoming dari SCELE UI lalu mempertahankan dua pesan Discord yang sama:

- `📚 JADWAL TUGAS`
- `🚨 DEADLINE HARI INI`

Bot bukan proses Discord yang hidup 24 jam. Setelah code di-push, GitHub Actions menjalankan script di runner GitHub dan laptop tidak perlu menyala.

## Activation pertama kali

State awal pada `state.json` adalah nonaktif. Jalankan **Actions → SCELE Assignments Checker → Run workflow**, pilih `activate: ON`, lalu jalankan workflow.

Bot akan mengambil data SCELE, membuat dua embed Discord, menyimpan dua message ID, lalu mengubah `active` menjadi `true`. Embed deadline tetap dibuat bila tidak ada deadline hari ini, dengan teks `✨ Tidak ada tugas yang deadline hari ini.`

Jika activation gagal pada scraping atau Discord, `active` tidak akan menjadi `true`. ID pesan yang sudah berhasil dibuat tetap disimpan agar activation berikutnya dapat melanjutkan tanpa membuat pesan duplikat. Menjalankan activation saat sudah aktif hanya menulis log dan tidak membuat pesan baru.

## Jadwal otomatis

Semua keputusan waktu memakai `Asia/Jakarta` di Python.

| Cron UTC | WIB | Aksi |
| --- | --- | --- |
| `0 17 * * *` | 00.00 | Edit pesan `📚 JADWAL TUGAS` |
| `0 3 * * *` | 10.00 | Edit pesan `🚨 DEADLINE HARI INI` |
| `0 5 * * *` | 12.00 | Edit pesan `📚 JADWAL TUGAS` |

Scheduled run saat bot masih inactive hanya menulis `Bot inactive. Skipping scheduled update.` Tidak ada scraping atau pesan Discord sampai activation manual berhasil.

Jika salah satu pesan persistent dihapus manual, Discord akan mengembalikan 404 ketika bot mencoba PATCH. Bot otomatis membuat pesan pengganti, menyimpan message ID baru ke `state.json`, dan workflow me-commit state tersebut.

## Tester mode

Mode lama `TESTER=ON` tetap tersedia untuk preview manual. Jalankan **Run workflow** dengan `tester: ON`; bot mengambil data SCELE asli dan membuat dua pesan preview dengan embed production yang sama. Tester tidak mengubah `state.json`, tidak mengaktifkan bot, dan tidak mengganggu update production berikutnya.

`activate` dan `tester` tidak boleh sama-sama `ON`.

## Konfigurasi lokal

Butuh Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Salin `.env.example` menjadi `.env`, lalu isi:

```env
SCELE_USERNAME=username_scele
SCELE_PASSWORD=password_scele
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TESTER=OFF
ACTIVATE=OFF
```

Jalankan lokal:

```powershell
python -m bot.main
pytest
```

`.env` diabaikan Git dan tidak boleh di-commit. Tidak ada avatar URL yang digunakan oleh bot.

## GitHub Secrets dan state

Tambahkan repository secrets berikut melalui **Settings → Secrets and variables → Actions**:

- `SCELE_USERNAME`
- `SCELE_PASSWORD`
- `DISCORD_WEBHOOK_URL`

Workflow memiliki `permissions: contents: write` dan me-commit `state.json` hanya bila berubah. Ini membuat message ID bertahan walaupun runner GitHub bersifat ephemeral. Pastikan repository mengizinkan `GITHUB_TOKEN` untuk read/write contents.

## Tampilan Discord

Schedule menggunakan embed biru (`3447003`); deadline hari ini menggunakan embed merah (`15158332`). Setiap tugas adalah satu field: course sebagai `🎓` field name, assignment bold, deadline `⏰`, serta link `[🔗 Buka Tugas]`. Parser mempertahankan `event_id`, course/activity URL, description, component, dan type; nama course display menghapus prefix `[SI.Reg]`/`[Reg]`, sedangkan title menghapus akhiran `is due`.

## Testing dan keterbatasan

Fixture lokal tidak membutuhkan login atau network. Test mencakup parsing, timezone WIB, sorting, embed kosong, activation, edit persistent message, recovery 404, dan tester mode.

SCELE saat diperiksa menggunakan form login Moodle dengan `logintoken`, username, dan password. Jika nantinya SCELE memerlukan CAPTCHA, MFA interaktif, SSO khusus, atau memblokir runner GitHub, login otomatis tidak dapat berjalan hanya dengan Secrets. Gunakan self-hosted runner yang diizinkan atau akses resmi dari pengelola SCELE; jangan menyimpan cookie jangka panjang.
