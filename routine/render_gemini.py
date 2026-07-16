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
    FFMPEG_BIN       explicit ffmpeg path (else `ffmpeg` on PATH, else imageio_ffmpeg)

Render-resume: each chunk's PCM is cached next to the output as
`<OUTBASE>.chunkNNN.pcm`. If a render dies partway (e.g. free-tier quota), just
re-run the SAME command — cached chunks are reused and only the missing ones hit
the API. Caches are deleted automatically on a fully successful render.

Notes:
- Gemini-TTS returns raw PCM: 24 kHz, signed 16-bit little-endian, mono.
- Multi-speaker config supports exactly 2 speakers; the speaker labels in the
  prompt MUST match the names in speaker_voice_configs ("Alex", "Sam").
- A global style instruction is prepended so delivery stays brisk and warm.
"""
import os, re, sys, json, time, base64, wave, shutil, subprocess, urllib.request, urllib.error, http.client

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
    "— measured, not peppy, not sleepy. Alex is the domain expert; Sam asks the questions. "
    "When a passage is in Mandarin Chinese or Tagalog, pronounce it authentically and "
    "natively — correct Mandarin tones, natural Tagalog vowels and stress — not with an "
    "English accent; switch cleanly back to English for the translations.")
STYLE = os.environ.get("STYLE", _DEFAULT_STYLE)
if ACCENT.strip():
    STYLE = STYLE + f" Their English delivery carries {ACCENT.strip()} accents (this applies to English only, not to the Mandarin or Tagalog)."

# ── voice priming (first-line fix for cross-chunk voice drift) ────────────────
# The script is rendered in several separate TTS calls (one per chunk, to respect
# the per-call output cap). Independent calls re-realize the two voices slightly
# differently, so the timbre "drifts" at chunk seams. This PRIME block is an
# explicit, IDENTICAL voice lock prepended to every call so each chunk re-anchors to
# the same two voices. It's prompt text — it adds NO extra requests, so it stays
# under the Gemini free-tier request-rate limit (unlike per-speaker rendering, the
# heavier escalation). Override/disable with VOICE_PRIME.
PRIME = os.environ.get("VOICE_PRIME",
    "VOICE LOCK — this is one continuous show; keep BOTH voices identical from the "
    "first line to the last. Alex is always one fixed voice: warm, measured, "
    "mid-pitched, female. Sam is always one fixed voice: deeper, steady, male. Never "
    "swap the two, never brighten or change their timbre, accent, or speaking rate "
    "between passages — render each speaker exactly the same in every part.")
STYLE = STYLE + " " + PRIME
# ─────────────────────────────────────────────────────────────────────────────
STYLE += "\n\n"

RATE, WIDTH, CHANNELS = 24000, 2, 1  # PCM format Gemini-TTS returns

# ── number normalization (TTS input only) ────────────────────────────────────
# The script is written with numerals (7,572 · 4.55% · $265B · 37 bps) so the
# transcript stays clean and readable. TTS pronunciation of bare digits/symbols is
# unreliable, so we expand numbers to words HERE, only in the text sent to the model
# — the script/transcript is never modified. Set NORMALIZE_NUMBERS=0 to disable.
_ONES = ["zero","one","two","three","four","five","six","seven","eight","nine","ten",
         "eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen",
         "eighteen","nineteen"]
_TENS = ["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]
_SCALES = [(10**12,"trillion"),(10**9,"billion"),(10**6,"million"),(10**3,"thousand")]

def _int_words(n):
    if n < 20: return _ONES[n]
    if n < 100: return _TENS[n//10] + (("-"+_ONES[n%10]) if n%10 else "")
    if n < 1000:
        return _ONES[n//100]+" hundred"+((" "+_int_words(n%100)) if n%100 else "")
    for val,name in _SCALES:
        if n >= val:
            return _int_words(n//val)+" "+name+((" "+_int_words(n%val)) if n%val else "")
    return str(n)

def _num_words(numstr):
    """'4.55' -> 'four point five five'; '7,572' -> 'seven thousand five hundred seventy-two'."""
    numstr = numstr.replace(",","")
    if "." in numstr:
        whole, frac = numstr.split(".", 1)
        w = _int_words(int(whole)) if whole not in ("","-") else "zero"
        return w + " point " + " ".join(_ONES[int(d)] for d in frac if d.isdigit())
    return _int_words(int(numstr))

def _year_words(y):
    """1900-2099 read as pairs: 2026 -> 'twenty twenty-six', 2001 -> 'two thousand one'."""
    hi, lo = y//100, y%100
    if lo == 0: return _int_words(hi)+" hundred"
    if lo < 10: return _int_words(hi)+" oh "+_ONES[lo] if False else _int_words(y)
    return _int_words(hi)+" "+_int_words(lo)

_SCALE_WORD = r"(?:trillion|billion|million|thousand)"
_N = r"\d(?:[\d,]*\d)?(?:\.\d+)?"   # comma-safe number: never captures a trailing comma
def normalize_numbers(text):
    if os.environ.get("NORMALIZE_NUMBERS","1") == "0":
        return text
    def money(m):
        cur = "dollars" if m.group("sym") == "$" else "euros"
        num = _num_words(m.group("num"))
        scale = (" "+m.group("scale")) if m.group("scale") else ""
        return f"{num}{scale} {cur}"
    # $265 billion / €120 million / $4.10
    text = re.sub(r"(?P<sym>[$€])(?P<num>"+_N+r")\s*(?P<scale>"+_SCALE_WORD+r")?",
                  money, text)
    # 6.4 percent / 0.38%
    text = re.sub(r"("+_N+r")\s*%", lambda m: _num_words(m.group(1))+" percent", text)
    # 37 bps / 25 bps
    text = re.sub(r"("+_N+r")\s*bps\b", lambda m: _num_words(m.group(1))+" basis points", text)
    # bare number + scale word: 706.6 billion
    text = re.sub(r"\b("+_N+r")\s+("+_SCALE_WORD+r")\b",
                  lambda m: _num_words(m.group(1))+" "+m.group(2), text)
    # years 1900-2099 (whole-word, no decimal/comma)
    text = re.sub(r"\b(?:19|20)\d{2}\b", lambda m: _year_words(int(m.group(0))), text)
    # any remaining number (decimals, comma-grouped, integers)
    text = re.sub(_N, lambda m: _num_words(m.group(0)), text)
    return text
# ─────────────────────────────────────────────────────────────────────────────

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
    """Group turns into chunks under the per-call budget. Returns a list of chunks,
    each a list of (speaker, text) turns — structure is kept so we can emit a timing
    sidecar (which turns landed in which chunk)."""
    chunks, cur, n = [], [], 0
    for sp, txt in turns:
        line = f"{sp}: {txt}\n"
        if cur and n + len(line) > budget:
            chunks.append(cur); cur, n = [], 0
        cur.append((sp, txt)); n += len(line)
    if cur: chunks.append(cur)
    return chunks


def dialogue_of(chunk):
    """Build the prompt text for a chunk, expanding numerals to words for the TTS."""
    return "".join(f"{sp}: {normalize_numbers(txt)}\n" for sp, txt in chunk)

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
    did_api = False
    timing_chunks = []   # per-chunk real audio windows → the sync sidecar
    cum = 0.0
    for i, ch in enumerate(chunks, 1):
        dlg = dialogue_of(ch)            # numerals expanded to words for the model
        cache = f"{OUTBASE}.chunk{i:03d}.pcm"
        if os.path.isfile(cache) and os.path.getsize(cache) > 0:
            print(f"  chunk {i}/{len(chunks)} — reusing cached render "
                  f"({os.path.getsize(cache)} bytes)", file=sys.stderr)
            data = open(cache, "rb").read()
        else:
            if did_api and REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)   # pace requests to respect free-tier RPM
            print(f"  rendering chunk {i}/{len(chunks)} ({len(dlg)} chars)…", file=sys.stderr)
            try:
                data = synth(dlg); did_api = True
            except RuntimeError as e:
                failed = (i, str(e))
                print(f"  ! chunk {i} failed: {e}", file=sys.stderr)
                print(f"  ! {i-1} chunk(s) cached — re-run the SAME command to resume "
                      f"from chunk {i} (cached chunks are NOT re-rendered).", file=sys.stderr)
                break
            with open(cache, "wb") as f:
                f.write(data)
        pcm += data
        dur = len(data) / (RATE * WIDTH * CHANNELS)
        timing_chunks.append({
            "startSec": round(cum, 2), "endSec": round(cum + dur, 2),
            "turns": [{"speaker": sp, "text": txt} for sp, txt in ch],
        })
        cum += dur
    if not pcm:
        die(failed[1] if failed else "no audio rendered")

    wav_path = OUTBASE + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(CHANNELS); w.setsampwidth(WIDTH); w.setframerate(RATE)
        w.writeframes(bytes(pcm))
    secs = len(pcm) / (RATE * WIDTH * CHANNELS)
    print(f"WAV → {wav_path}  (~{secs/60:.1f} min)", file=sys.stderr)

    # sync sidecar: real per-chunk audio windows so build_episode.py can anchor the
    # transcript to actual audio positions (accurate) instead of a global char guess.
    timing_path = OUTBASE + ".timing.json"
    json.dump({"durationSec": round(secs, 2), "chunks": timing_chunks},
              open(timing_path, "w"), ensure_ascii=False, indent=1)
    print(f"TIMING → {timing_path}  ({len(timing_chunks)} chunk anchor(s))", file=sys.stderr)

    ff = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ff:
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

    if not failed:
        # full render succeeded — drop the per-chunk resume caches
        for i in range(1, len(chunks) + 1):
            c = f"{OUTBASE}.chunk{i:03d}.pcm"
            if os.path.isfile(c):
                try:
                    os.remove(c)
                except OSError:
                    pass

    if failed:
        print(f"\nPARTIAL: stopped at chunk {failed[0]}/{len(chunks)} — {failed[1]}\n"
              f"Re-run the SAME command to resume from chunk {failed[0]} "
              f"(cached chunks are reused — no re-render, no wasted quota).", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
