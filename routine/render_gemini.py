#!/usr/bin/env python3
"""
render_gemini.py — render a two-host script to audio via Gemini-TTS multi-speaker.

Reads a script .md, extracts the ALEX:/SAM: turns, chunks them under a per-call
budget (Gemini-TTS multi-speaker takes both speakers in ONE prompt), synthesizes
each chunk, concatenates the raw PCM, and writes a single WAV (+ MP3 if ffmpeg
is present).

Usage:
    GEMINI_API_KEY=...  python3 render_gemini.py \
        [script.md] [out_basename]

Defaults to today's two-host script in this folder.

Env:
    GEMINI_API_KEY   (required)
    GEMINI_TTS_MODEL default: gemini-2.5-flash-preview-tts
                     (swap to gemini-3.1-flash-tts-preview when GA on your key)
    VOICE_ALEX       default: Charon   (steady/authoritative — Host A, expert)
    VOICE_SAM        default: Puck     (brighter/curious     — Host B, generalist)
    CHUNK_CHARS      default: 2600      (chars of dialogue per API call)

Notes:
- Gemini-TTS returns raw PCM: 24 kHz, signed 16-bit little-endian, mono.
- Multi-speaker config supports exactly 2 speakers; the speaker labels in the
  prompt MUST match the names in speaker_voice_configs ("Alex", "Sam").
- A global style instruction is prepended so delivery stays brisk and warm.
"""
import os, re, sys, json, time, base64, wave, subprocess, urllib.request, urllib.error, http.client

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = __import__("datetime").date.today().isoformat()

SCRIPT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, f"commute-two-host-script-{TODAY}.md")
OUTBASE = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, f"commute-gemini-{TODAY}")

API_KEY   = os.environ.get("GEMINI_API_KEY")
MODEL     = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
VOICE_ALEX = os.environ.get("VOICE_ALEX", "Sulafat")   # Host A, expert (female)
VOICE_SAM  = os.environ.get("VOICE_SAM", "Charon")     # Host B, generalist (deep male)
ACCENT     = os.environ.get("ACCENT", "British English")
CHUNK_CHARS = int(os.environ.get("CHUNK_CHARS", "7000"))   # chars of dialogue per call. 7000 ≈ 14 min audio/call (3 calls for a ~37-min show); set 4000 for ~8 min/call (5 calls) to stay well under the per-call output cap.
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "30"))  # seconds between calls — paces free-tier RPM
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "4"))         # retries on 429 / 5xx with backoff

_DEFAULT_STYLE = ("Two polished financial-news anchors, as on a Bloomberg or FT broadcast. "
    "Crisp, confident, authoritative and professional. Controlled energy and clean diction "
    "— measured, not peppy, not sleepy. Alex is the domain expert; Sam asks the questions.")
STYLE = os.environ.get("STYLE", _DEFAULT_STYLE)
if ACCENT.strip():
    STYLE = STYLE + f" Both hosts speak with {ACCENT.strip()} accents."
STYLE += "\n\n"

RATE, WIDTH, CHANNELS = 24000, 2, 1  # PCM format Gemini-TTS returns

def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr); sys.exit(code)

def extract_turns(path):
    if not os.path.isfile(path): die(f"script not found: {path}")
    turns = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\s*(ALEX|SAM)\s*:\s*(.+?)\s*$", line)
        if m:
            speaker = "Alex" if m.group(1) == "ALEX" else "Sam"
            turns.append((speaker, m.group(2)))
    if not turns: die("no ALEX:/SAM: turns found in script")
    return turns

def chunk_turns(turns, budget):
    chunks, cur, n = [], [], 0
    for sp, txt in turns:
        line = f"{sp}: {txt}\n"
        if cur and n + len(line) > budget:
            chunks.append("".join(cur)); cur, n = [], 0
        cur.append(line); n += len(line)
    if cur: chunks.append("".join(cur))
    return chunks

def synth(dialogue):
    """Return raw PCM bytes for one multi-speaker chunk."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
           f"?key={API_KEY}")
    body = {
        "contents": [{"parts": [{"text": STYLE + "TTS the following conversation:\n" + dialogue}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "multiSpeakerVoiceConfig": {
                    "speakerVoiceConfigs": [
                        {"speaker": "Alex",
                         "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE_ALEX}}},
                        {"speaker": "Sam",
                         "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE_SAM}}},
                    ]
                }
            },
        },
    }
    data = json.dumps(body).encode()
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:500]
            # retry transient throttling / server errors with exponential backoff
            if e.code in (429, 500, 503) and attempt < MAX_RETRIES:
                wait = REQUEST_DELAY * (2 ** attempt)
                print(f"    {e.code} (attempt {attempt+1}/{MAX_RETRIES}); backing off {wait:.0f}s…",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"API {e.code}: {msg}")
        except (urllib.error.URLError, http.client.IncompleteRead, http.client.HTTPException,
                ConnectionError, TimeoutError) as e:
            # transient network / proxy drop (e.g. IncompleteRead on a large
            # streamed response) — back off and retry the whole request.
            if attempt < MAX_RETRIES:
                wait = REQUEST_DELAY * (2 ** attempt)
                print(f"    network error '{type(e).__name__}' (attempt {attempt+1}/{MAX_RETRIES}); "
                      f"backing off {wait:.0f}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"network error after retries: {e}")
    try:
        b64 = resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError):
        raise RuntimeError(f"unexpected response: {json.dumps(resp)[:500]}")
    return base64.b64decode(b64)

def main():
    if not API_KEY: die("GEMINI_API_KEY not set")
    turns = extract_turns(SCRIPT)
    chunks = chunk_turns(turns, CHUNK_CHARS)
    print(f"{len(turns)} turns → {len(chunks)} chunk(s) | model={MODEL} "
          f"| Alex={VOICE_ALEX} Sam={VOICE_SAM}", file=sys.stderr)

    pcm = bytearray()
    failed = None
    for i, ch in enumerate(chunks, 1):
        if i > 1 and REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)   # pace requests to respect free-tier RPM
        print(f"  rendering chunk {i}/{len(chunks)} ({len(ch)} chars)…", file=sys.stderr)
        try:
            pcm += synth(ch)
        except RuntimeError as e:
            failed = (i, str(e))
            print(f"  ! chunk {i} failed: {e}", file=sys.stderr)
            print(f"  ! saving the {i-1} chunk(s) already rendered and stopping.", file=sys.stderr)
            break
    if not pcm:
        die(failed[1] if failed else "no audio rendered")

    wav_path = OUTBASE + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(CHANNELS); w.setsampwidth(WIDTH); w.setframerate(RATE)
        w.writeframes(bytes(pcm))
    secs = len(pcm) / (RATE * WIDTH * CHANNELS)
    print(f"WAV → {wav_path}  (~{secs/60:.1f} min)", file=sys.stderr)

    ff = None
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0:
        ff = "ffmpeg"
    else:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    if ff:
        mp3_path = OUTBASE + ".mp3"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", wav_path,
                        "-b:a", "96k", mp3_path], check=True)
        print(f"MP3 → {mp3_path}", file=sys.stderr)
    else:
        print("ffmpeg not found — kept WAV only.", file=sys.stderr)

    if failed:
        print(f"\nPARTIAL: stopped at chunk {failed[0]}/{len(chunks)} — {failed[1]}\n"
              f"Re-run after fixing to render the full episode.", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
