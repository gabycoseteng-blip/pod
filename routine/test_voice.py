#!/usr/bin/env python3
"""
test_voice.py — render a short sample so you can audition a Gemini-TTS voice.

Single voice:
    GEMINI_API_KEY=... python3 test_voice.py Charon
    GEMINI_API_KEY=... python3 test_voice.py Puck "Markets opened lower today."

Two-host sample (hear Alex vs Sam together):
    GEMINI_API_KEY=... python3 test_voice.py --pair Charon Puck

Recommended voices to try:
    Steady/authoritative (Host A): Charon, Kore, Algenib, Iapetus
    Bright/curious (Host B):       Puck, Aoede, Zephyr, Leda
Output: sample_<voice>.wav  (or sample_pair.wav)
"""
import os, sys, json, base64, wave, urllib.request, urllib.error

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL   = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
RATE, WIDTH, CH = 24000, 2, 1
DEFAULT_LINE = ("The power grid is six gigawatts short, oil is sliding on the Iran deal, "
                "and the peso just touched a record low. Welcome to The Morning Commute.")

def die(m): print(f"ERROR: {m}", file=sys.stderr); sys.exit(1)

def call(body, out):
    if not API_KEY: die("GEMINI_API_KEY not set")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
           f":generateContent?key={API_KEY}")
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        die(f"API {e.code}: {e.read().decode()[:400]}")
    try:
        pcm = base64.b64decode(
            data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except Exception:
        die(f"unexpected response: {json.dumps(data)[:400]}")
    with wave.open(out, "wb") as w:
        w.setnchannels(CH); w.setsampwidth(WIDTH); w.setframerate(RATE)
        w.writeframes(pcm)
    print(f"OK → {out}  ({len(pcm)/(RATE*WIDTH*CH):.1f}s)", file=sys.stderr)

def single(voice, line):
    body = {"contents": [{"parts": [{"text": "Say warmly: " + line}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    call(body, f"sample_{voice}.wav")

def pair(a, b):
    accent = os.environ.get("ACCENT", "").strip()
    accent_line = f" Both hosts speak with {accent} accents." if accent else ""
    style = os.environ.get("STYLE",
        "Calm, measured, low-key conversation between two hosts. Relaxed, even pacing; "
        "understated and grounded; NOT peppy, perky, or high-energy. Thoughtful and easy.")
    convo = ("Alex: Good morning — oil is sliding on the Iran deal.\n"
             "Sam: Wait, so does that finally take pressure off inflation?\n"
             "Alex: Exactly. That's the whole story this week.\n")
    body = {"contents": [{"parts": [{"text":
                style + accent_line +
                "\nTTS the following conversation:\n" + convo}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                    {"speaker": "Alex", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a}}},
                    {"speaker": "Sam",  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": b}}},
                ]}}}}
    call(body, "sample_pair.wav")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--pair":
        if len(args) < 3: die("usage: test_voice.py --pair <VoiceA> <VoiceB>")
        pair(args[1], args[2])
    else:
        voice = args[0] if args else "Charon"
        line = args[1] if len(args) > 1 else DEFAULT_LINE
        single(voice, line)
