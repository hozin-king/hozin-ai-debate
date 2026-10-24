# Debat AI: Bumi Bulat vs Bumi Datar

Dua kubu AI berdebat dengan **giliran ketat**: satu kubu harus selesai
penuh dulu, baru kubu lawan menjawab — tidak ada yang memotong. Episode
baru digerakkan otomatis oleh GitHub Actions, tersimpan sebagai JSON,
dan dibaca halaman statis. Kedua kubu diperankan AI untuk hiburan dan
edukasi; argumen kubu Datar adalah peran debat, bukan klaim faktual
halaman ini.

## Halaman debat (live)

- **GitHub Pages:** https://hozin-king.github.io/hozin-ai-debate/
- **Mount hozinking.my.id (belum diterapkan):** potongan siap pakai ada di
  `mount/hozinking-debat-route.js` — pemilik worker `hozinwate-web`
  tinggal menempelkannya agar `https://hozinking.my.id/debat` mem-proxy
  halaman ini. Repo/worker lain **tidak diubah** oleh proyek ini.

## Cara kerja

1. Workflow `.github/workflows/debate.yml` jalan tiap hari **07:00 WIB**
   (cron `0 0 * * *` UTC) + bisa dipicu manual (`workflow_dispatch`).
2. `engine/generate.py` (stdlib saja, tanpa dependensi) memanggil
   `POST https://gateway.dahono.com/v1/chat/completions` secara
   **berurutan**: giliran N+1 baru diminta setelah respons giliran N
   diterima utuh dan tervalidasi. Satu run = satu episode penuh:
   **12 giliran (6 per kubu)**, tiap giliran dibatasi ±700 karakter.
3. Hasilnya di-commit ke `docs/data/episodes/episode-NNN.json` dan
   indeks `docs/data/index.json`; halaman membaca JSON itu.
4. Bila API gagal di tengah episode, episode disimpan berstatus
   `partial` apa adanya — **tidak ada giliran karangan**.
5. Repo ini **publik** supaya Actions gratis (kuota repo privat habis
   sampai 1 Nov 2026).

## Format JSON history

`docs/data/index.json`:

```json
{
  "version": 1,
  "updated_at": "2026-10-24T00:00:00Z",
  "latest_episode_id": "episode-001",
  "episodes": [
    { "id": "episode-001", "title": "Debat #1: ...", "topic": "...",
      "status": "live | partial | sample", "turns": 12,
      "file": "episodes/episode-001.json" }
  ]
}
```

`docs/data/episodes/episode-NNN.json`:

```json
{
  "id": "episode-001", "title": "Debat #1: ...", "topic": "...",
  "status": "live", "turns_per_side": 6,
  "models": { "bulat": "<id model yang benar-benar dipakai>",
              "datar": "<id model yang benar-benar dipakai>" },
  "turns": [
    { "n": 1, "side": "bulat | datar",
      "speaker": "Kubu Bumi Bulat | Kubu Bumi Datar",
      "model": "<id model>", "text": "..." }
  ]
}
```

Halaman menampilkan **30 giliran terbaru dulu** (tombol "Muat giliran
lebih lama" untuk sisanya) dan arsip episode bisa dibuka dari awal —
tidak ada framework, JSON kecil, jadi anti-lag.

## Model

- Engine memakai API OpenAI-compatible Dahono
  (`https://gateway.dahono.com/v1`, endpoint `/v1/chat/completions`)
  dengan **dua model berbeda** supaya dua kubu terasa beda suaranya.
- Model yang diminta bisa di-set lewat repo variables `MODEL_BULAT`
  dan `MODEL_DATAR` (Settings → Secrets and variables → Variables).
  Bila kosong atau tidak ada di daftar `GET /v1/models`, engine jatuh
  ke heuristik (id mengandung `deepseek` untuk Bulat, `qwen` untuk
  Datar) lalu ke dua model pertama yang berbeda — dan **model yang
  benar-benar dipakai selalu dicatat di tiap episode JSON**. Itulah
  sumber kebenaran; user bisa mengganti pilihan belakangan lewat
  variables tanpa mengubah kode.
- Default awal: Bulat condong ke keluarga DeepSeek, Datar condong ke
  keluarga Qwen (lihat heuristik di `engine/generate.py`).

## Wiring secret (status: MENUNGGU)

Engine membaca API key **hanya** dari GitHub Actions secrets — tidak
ada key di kode, data, log, maupun laporan mana pun:

- `DAHONO_API_KEY` → kubu Bumi Bulat
- `DAHONO_API_KEY_2` → kubu Bumi Datar

Cara mengisi: repo → Settings → Secrets and variables → Actions →
New repository secret (satu per nama di atas). Setelah keduanya terisi,
jalankan workflow manual dengan mode `check` untuk validasi wiring,
lalu mode `generate` untuk episode live pertama.

**Status saat rilis awal: wiring secret belum terverifikasi dari sisi
agen pembangun** — halaman tayang dengan **episode contoh**
(`episode-000-contoh`, berlabel CONTOH jelas, ditulis sebagai
placeholder format, bukan debat live). Begitu kedua secret terisi dan
mode `check` lolos, episode live pertama akan menggantikan posisi
teratas secara otomatis pada jadwal berikutnya (atau lewat pemicu
manual). Workflow **tidak merah** bila secret belum tersedia — engine
berhenti bersih dengan status skipped.

## Kontrak preview untuk aplikasi Hozin Tools (belum diterapkan di app)

Integrasi aplikasi **tidak dikerjakan di sini** — menyentuh jalur
rilis-kritis aplikasi + repo lain, di luar batas proyek ini. Kontrak
data untuk tim aplikasi:

- **Preview endpoint:** `https://hozin-king.github.io/hozin-ai-debate/data/index.json`
- **Preview yang ditampilkan di kotak header card:**
  `latest_episode_id`, judul + topik episode terbaru, `status`, jumlah
  giliran; cuplikan = giliran terakhir episode terbaru dari
  `data/episodes/<id>.json` (potong ±120 karakter).
- **Klik preview → debat lengkap:** buka URL halaman + parameter
  `?episode=<id>` (mis. `.../hozin-ai-debate/?episode=episode-001`).
- Item lama di area kotak itu (header card + "Lihat Log" +
  "Lihat Manifest") boleh dihapus/ditata ulang oleh tim aplikasi
  sesuai pesanan user; halaman debat tidak bergantung pada aplikasi.

## Yang tidak dibangun

- Telegram = fase 2, belum dibangun.
- Tidak ada build/push APK di proyek ini.
- Tidak ada penulisan ke D1 — data tinggal di repo (cukup untuk beban
  ini, tanpa membakar kuota Worker).
