#!/usr/bin/env python3
"""Debat AI — posting episode terbaru ke Telegram (satu episode = satu post).

Aturan posting:
- Hanya episode berstatus "live" atau "partial". Episode berstatus
  "sample" (mis. episode-000-contoh) SELALU dilewati, tidak pernah diposting.
- Anti-dobel: docs/data/telegram_posted.json berisi daftar id episode yang
  sudah diposting. Bila file belum ada, dianggap kosong. Id yang sudah ada
  di daftar dilewati (exit 0, tanpa kirim ulang).
- Satu run hanya memposting episode terbaru (latest_episode_id di index),
  bukan memindai mundur ke episode lama.

Kredensial: dibaca HANYA dari environment (GitHub Actions secrets
TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID). Script ini TIDAK PERNAH
mencetak, me-log, atau menulis nilai secret apa pun — hanya status
ada/tidak ada. Bila salah satu secret tidak tersedia, script keluar
bersih (exit 0) dengan pesan skip supaya workflow tidak merah karenanya.

Pengiriman: POST https://api.telegram.org/bot<TOKEN>/sendMessage dengan
chat_id + text, plain text TANPA parse_mode (menghindari masalah
escaping). Bila pengiriman gagal (error API), posted file TIDAK diupdate
dan script keluar non-zero agar kegagalan terlihat; log hanya berisi
status/error type, TIDAK PERNAH isi respons API.

Setelah posting sukses, script menambahkan id episode ke
telegram_posted.json; workflow yang meng-commit file itu kembali ke main.

Mode dry-run: `python3 engine/telegram_post.py --dry-run` menampilkan
pesan yang akan dikirim TANPA mengirim dan TANPA mengubah data apa pun.
Tanpa flag, mode tanpa secret keluar skip bersih (exit 0).

Hanya memakai stdlib (urllib) agar workflow tidak butuh instalasi paket.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(REPO_ROOT, "docs", "data")
SITE_URL = "https://hozin-king.github.io/hozin-ai-debate"
SNIPPET_CHARS = 120
TIMEOUT_S = 30


def load_index(data_dir):
    path = os.path.join(data_dir, "index.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def latest_episode(index):
    episodes = index.get("episodes", [])
    if not episodes:
        return None
    latest_id = index.get("latest_episode_id")
    if latest_id:
        for ep in episodes:
            if ep.get("id") == latest_id:
                return ep
    return episodes[-1]


def load_posted(data_dir):
    path = os.path.join(data_dir, "telegram_posted.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        for key in ("posted", "episodes", "ids"):
            if isinstance(data.get(key), list):
                return [str(x) for x in data[key]]
    return []


def save_posted(data_dir, posted):
    path = os.path.join(data_dir, "telegram_posted.json")
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sorted(set(posted)), fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_episode_file(data_dir, episode):
    rel = episode.get("file", "")
    if not rel:
        return None
    path = os.path.join(data_dir, rel)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def snippet_from_episode(episode_doc, episode):
    turns = []
    if isinstance(episode_doc, dict):
        turns = episode_doc.get("turns", []) or []
    if turns:
        last = turns[-1]
        text = last.get("text", "") if isinstance(last, dict) else str(last)
    else:
        text = episode.get("topic", "") or ""
    text = " ".join(str(text).split())
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text[:SNIPPET_CHARS]
    idx = cut.rfind(" ")
    if idx > SNIPPET_CHARS // 2:
        cut = cut[:idx]
    return cut.rstrip() + "…"


def build_message(episode, snippet):
    lines = [
        "🗣️ Debat AI: " + str(episode.get("title", episode.get("id", ""))),
        "Status: " + str(episode.get("status", "")),
    ]
    topic = episode.get("topic", "")
    if topic:
        lines.append("Topik: " + str(topic))
    if snippet:
        lines.append('Cuplikan giliran terakhir: "' + snippet + '"')
    lines.append("🔗 " + SITE_URL + "/?episode=" + str(episode.get("id", "")))
    return "\n".join(lines)


def send_telegram(token, chat_id, text):
    # URL berisi token — JANGAN PERNAH dicetak / di-log.
    url = "https://api.telegram.org/bot" + token + "/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "hozin-ai-debate/1.0")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                raise RuntimeError("Telegram API mengembalikan ok=false")
            return True
    except urllib.error.HTTPError as e:
        # Hanya status + tipe error; isi respons TIDAK PERNAH dicetak.
        raise RuntimeError(f"Telegram API HTTP {e.code}")
    except Exception as e:
        raise RuntimeError(f"gagal kirim ke Telegram: {type(e).__name__}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Posting episode debat terbaru ke Telegram."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="tampilkan pesan yang akan dikirim tanpa mengirim / mengubah data",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="direktori data (default: docs/data repo ini; untuk uji lokal)",
    )
    args = parser.parse_args(argv)
    data_dir = args.data_dir

    try:
        index = load_index(data_dir)
    except (OSError, ValueError) as e:
        print(f"[error] tidak bisa membaca index.json: {type(e).__name__}")
        return 1

    episode = latest_episode(index)
    if episode is None:
        print("[skipped] tidak ada episode di index.json.")
        return 0

    ep_id = str(episode.get("id", ""))
    status = str(episode.get("status", ""))
    print(f"[info] episode terbaru: {ep_id} (status: {status})")

    # Sample SELALU dilewati — sebelum cek secret maupun posted.
    if status != "live" and status != "partial":
        print(f"[skipped] status '{status}' bukan live/partial — dilewati.")
        return 0

    posted = load_posted(data_dir)
    if ep_id in posted:
        print(f"[skipped] {ep_id} sudah pernah diposting — anti-dobel aktif.")
        return 0

    episode_doc = load_episode_file(data_dir, episode)
    snippet = snippet_from_episode(episode_doc, episode)
    message = build_message(episode, snippet)

    if args.dry_run:
        print("[dry-run] pesan yang akan dikirim (tidak dikirim, data tidak diubah):")
        print("---")
        print(message)
        print("---")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    # Hanya presence boolean — nilai secret TIDAK PERNAH dicetak.
    print(f"[info] TELEGRAM_BOT_TOKEN ada: {bool(token)}")
    print(f"[info] TELEGRAM_CHAT_ID ada: {bool(chat_id)}")
    if not token or not chat_id:
        missing = []
        if not token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        print(f"[skipped] secret belum tersedia: {', '.join(missing)}")
        print("[skipped] job menunggu token bot + chat id dari user.")
        return 0

    try:
        send_telegram(token, chat_id, message)
    except RuntimeError as e:
        # posted file TIDAK diupdate; kegagalan terlihat via exit non-zero.
        print(f"[error] {e}")
        return 1

    posted.append(ep_id)
    save_posted(data_dir, posted)
    print(f"[done] {ep_id} diposting ke Telegram; telegram_posted.json diperbarui.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
