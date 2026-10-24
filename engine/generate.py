#!/usr/bin/env python3
"""Debat AI Bumi Bulat vs Bumi Datar — engine GitHub Actions.

Satu run = satu episode penuh (12 giliran: 6 per kubu), dengan giliran
KETAT: giliran N+1 baru diminta SETELAH respons giliran N diterima utuh
dan tervalidasi. Tidak ada paralelisme, tidak ada giliran karangan.

Kredensial: dibaca HANYA dari environment (GitHub Actions secrets
DAHONO_API_KEY dan DAHONO_API_KEY_2). Script ini TIDAK PERNAH mencetak,
me-log, atau menulis nilai secret apa pun — hanya status (ada/tidak ada)
dan nama endpoint. Bila secret tidak tersedia, engine berhenti dengan
status "skipped" (exit 0) supaya workflow tidak merah karenanya; episode
contoh tetap tayang di halaman.

Pemilihan model: nama model yang diminta (env MODEL_BULAT / MODEL_DATAR,
boleh kosong) diverifikasi ke GET /v1/models. Bila nama yang diminta
tidak ada di daftar, engine jatuh ke heuristik (id mengandung
"deepseek" untuk kubu Bulat, "qwen" untuk kubu Datar) lalu ke dua model
pertama yang berbeda dari daftar. Model yang BENAR-BENAR dipakai dicatat
di tiap episode JSON — itulah sumber kebenaran, bukan default di sini.

Hanya memakai stdlib (urllib) agar workflow tidak butuh instalasi paket.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

GATEWAY = "https://gateway.dahono.com/v1"
DATA_DIR = os.path.join("docs", "data")
EPISODES_DIR = os.path.join(DATA_DIR, "episodes")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")

TURNS_PER_SIDE = 6
MAX_CHARS = 700
MAX_TOKENS = 450
TEMPERATURE = 0.8
TIMEOUT_S = 120

TOPICS = [
    "Foto Bumi dari luar angkasa dan bentuk planet yang terlihat",
    "Bayangan Bumi saat gerhana bulan",
    "Kapal yang menghilang di horizon dan lengkung laut",
    "Penerbangan dan rute lintas kutub",
    "Satelit, GPS, dan stasiun luar angkasa",
    "Air laut yang selalu datar dan permukaan air",
    "Matahari terbenam dan zona waktu",
    "Bintang yang terlihat berbeda di belahan bumi utara dan selatan",
]

PERSONA_BULAT = (
    "Kamu adalah 'Kubu Bumi Bulat' dalam debat hiburan/edukasi berbahasa "
    "Indonesia. Kamu berargumen bahwa Bumi berbentuk bulat pepat (oblate "
    "spheroid) berdasarkan bukti ilmiah: foto dari luar angkasa, bayangan "
    "bulat saat gerhana bulan, kapal yang hilang di horizon, penerbangan "
    "lintas kutub, GPS dan satelit. Gayamu tenang, berbasis bukti, dan "
    "menghormati lawan. Jawab dalam Bahasa Indonesia, langsung ke argumen, "
    "tanggapi argumen lawan terakhir secara spesifik, jangan mengulang "
    "kalimat yang sama, jangan menyerang pribadi, jangan keluar dari peran."
)

PERSONA_DATAR = (
    "Kamu adalah 'Kubu Bumi Datar' dalam debat hiburan/edukasi berbahasa "
    "Indonesia. Kamu MEMERANKAN posisi bahwa Bumi itu datar: horizon "
    "terlihat datar, air selalu mencari permukaan datar, lengkungan tidak "
    "pernah terlihat mata, foto luar angkasa bisa direkayasa. Ini peran "
    "debat, bukan klaim faktual halaman ini. Gayamu tenang dan menghormati "
    "lawan. Jawab dalam Bahasa Indonesia, langsung ke argumen, tanggapi "
    "argumen lawan terakhir secara spesifik, jangan mengulang kalimat yang "
    "sama, jangan menyerang pribadi, jangan keluar dari peran."
)


def _req(method, path, key=None, payload=None):
    req = urllib.request.Request(GATEWAY + path, method=method)
    req.add_header("User-Agent", "hozin-ai-debate/1.0")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=TIMEOUT_S) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()[:300]
        except Exception:
            body = ""
        # Hanya status + potongan error generik; TIDAK PERNAH isi header/key.
        raise RuntimeError(f"HTTP {e.code} pada {method} {path}: {body}")
    except Exception as e:
        raise RuntimeError(f"gagal {method} {path}: {type(e).__name__}")


def list_models(key):
    _, body = _req("GET", "/models", key=key)
    ids = []
    for item in body.get("data", []) if isinstance(body, dict) else []:
        mid = item.get("id") if isinstance(item, dict) else None
        if mid:
            ids.append(mid)
    return ids


def resolve_model(wanted, available, prefer_substr, fallback_index):
    if wanted and wanted in available:
        return wanted
    if wanted:
        print(f"  [info] model yang diminta tidak ada di daftar, cari pengganti")
    for mid in available:
        if prefer_substr in mid.lower():
            return mid
    if len(available) > fallback_index:
        return available[fallback_index]
    return available[0] if available else None


def chat(key, model, system_prompt, history_text, last_opponent):
    if last_opponent:
        user_msg = (
            f"Argumen lawan terakhir:\n{last_opponent}\n\n"
            f"Debat sejauh ini (ringkas):\n{history_text}\n\n"
            "Sekarang giliranmu. Jawab dalam Bahasa Indonesia, maksimal "
            "sekitar 600 karakter, langsung ke argumen dan tanggapi poin "
            "lawan di atas. Satu jawaban utuh, tanpa daftar panjang."
        )
    else:
        user_msg = (
            f"Debat dimulai. Topik episode ini dijabarkan di bawah.\n"
            f"{history_text}\n\n"
            "Kamu membuka debat. Jawab dalam Bahasa Indonesia, maksimal "
            "sekitar 600 karakter, langsung ke argumen pembuka. "
            "Satu jawaban utuh, tanpa daftar panjang."
        )
    _, body = _req(
        "POST",
        "/chat/completions",
        key=key,
        payload={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        },
    )
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("respons chat tidak berisi teks jawaban")
    # Sebagian model kadang mengembalikan content=None (mis. keluaran
    # reasoning-only / tool-call tanpa teks). Itu harus jadi kegagalan
    # yang bisa di-retry (RuntimeError), BUKAN crash AttributeError —
    # kalau tidak, satu giliran kosong menggagalkan seluruh run dan
    # episode yang sudah terkumpul ikut hilang (insiden episode-002).
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("respons chat kosong")
    return truncate(content.strip())


def truncate(text):
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    # Potong di akhir kalimat terakhir bila ada, supaya tidak menggantung.
    for sep in (". ", "! ", "? ", "\n"):
        idx = cut.rfind(sep)
        if idx > MAX_CHARS // 2:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def load_index():
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def next_episode_no(index):
    nums = []
    for ep in index.get("episodes", []):
        eid = str(ep.get("id", ""))
        if eid.startswith("episode-") and eid[8:11].isdigit():
            nums.append(int(eid[8:11]))
    return max(nums, default=0) + 1


def main():
    key_bulat = os.environ.get("DAHONO_API_KEY", "")
    key_datar = os.environ.get("DAHONO_API_KEY_2", "")
    if not key_bulat or not key_datar:
        missing = []
        if not key_bulat:
            missing.append("DAHONO_API_KEY")
        if not key_datar:
            missing.append("DAHONO_API_KEY_2")
        print(f"[skipped] secret belum tersedia: {', '.join(missing)}")
        print("[skipped] episode contoh tetap tayang; wiring secret menunggu.")
        return 0

    print("[info] kedua secret tersedia (nilai tidak pernah dicetak).")
    models_bulat = list_models(key_bulat)
    models_datar = list_models(key_datar)
    model_bulat = resolve_model(
        os.environ.get("MODEL_BULAT", ""), models_bulat, "deepseek", 0
    )
    model_datar = resolve_model(
        os.environ.get("MODEL_DATAR", ""), models_datar, "qwen", 1
    )
    if not model_bulat or not model_datar:
        print("[error] daftar model kosong, tidak bisa memilih model.")
        return 1
    print(f"[info] model kubu Bulat terpilih dari daftar (dicatat di JSON).")
    print(f"[info] model kubu Datar terpilih dari daftar (dicatat di JSON).")

    index = load_index()
    ep_no = next_episode_no(index)
    topic = TOPICS[(ep_no - 1) % len(TOPICS)]
    ep_id = f"episode-{ep_no:03d}"
    starter = "bulat" if ep_no % 2 == 1 else "datar"
    print(f"[info] membuat {ep_id} — topik: {topic} — pembuka: {starter}")

    turns = []
    history_bits = [f"Topik: {topic}."]
    last = {"bulat": None, "datar": None}
    other = "datar" if starter == "bulat" else "bulat"
    order = [starter if i % 2 == 0 else other
             for i in range(TURNS_PER_SIDE * 2)]
    # Giliran KETAT: loop berurutan, tiap panggilan menunggu respons utuh.
    status = "complete"
    for n, side in enumerate(order, start=1):
        key = key_bulat if side == "bulat" else key_datar
        model = model_bulat if side == "bulat" else model_datar
        system = PERSONA_BULAT if side == "bulat" else PERSONA_DATAR
        opponent = "datar" if side == "bulat" else "bulat"
        last_text = None
        for attempt in range(3):
            try:
                last_text = chat(
                    key, model, system,
                    " ".join(history_bits[-6:]), last[opponent],
                )
                break
            except RuntimeError as e:
                print(f"  [retry] giliran {n} ({side}) percobaan {attempt + 1}: {e}")
                time.sleep(5 * (attempt + 1))
        if last_text is None:
            print(f"[partial] {ep_id} berhenti di giliran {n} ({side}).")
            status = "partial"
            break
        turns.append({
            "n": n,
            "side": side,
            "speaker": "Kubu Bumi Bulat" if side == "bulat" else "Kubu Bumi Datar",
            "model": model,
            "text": last_text,
        })
        last[side] = last_text
        history_bits.append(f"{side}: {last_text[:220]}")
        print(f"  [ok] giliran {n}/{len(order)} ({side}) — {len(last_text)} karakter")

    episode = {
        "id": ep_id,
        "title": f"Debat #{ep_no}: {topic}",
        "topic": topic,
        "status": "live" if status == "complete" else "partial",
        "turns_per_side": TURNS_PER_SIDE,
        "turns": turns,
        "models": {"bulat": model_bulat, "datar": model_datar},
        "generated_by": "github-actions",
        "note": "Kedua kubu diperankan AI untuk hiburan/edukasi.",
    }
    os.makedirs(EPISODES_DIR, exist_ok=True)
    ep_path = os.path.join(EPISODES_DIR, f"{ep_id}.json")
    with open(ep_path, "w", encoding="utf-8") as fh:
        json.dump(episode, fh, ensure_ascii=False, indent=2)
    index["episodes"] = [e for e in index.get("episodes", [])
                          if e.get("id") != ep_id]
    index["episodes"].append({
        "id": ep_id,
        "title": episode["title"],
        "topic": topic,
        "status": episode["status"],
        "turns": len(turns),
        "file": f"episodes/{ep_id}.json",
    })
    index["episodes"].sort(key=lambda e: e["id"])
    index["latest_episode_id"] = ep_id
    index["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)
    print(f"[done] {ep_id}: {len(turns)} giliran, status={episode['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
