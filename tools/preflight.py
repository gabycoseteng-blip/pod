#!/usr/bin/env python3
"""
preflight.py — run-start gate for the daily routine: verify everything the run
will need BEFORE any research or rendering happens.

Why this exists: the expensive failures all announce themselves LATE. A wrong
R2_BUCKET fails at upload (after the full render), a dead GEMINI_API_KEY or a
deprecated TTS model fails at render (after the full research pass), and a
missing ffmpeg fails at the MP3 step. Each of those is a 5-second check at
minute zero. Run this at step 0 of /morning-commute and read the verdict:

    exit 0  — all clear (warnings, if any, are printed; the run may proceed)
    exit 3  — AUDIO-side failure only (Gemini/R2/ffmpeg/disk): do the TEXT
              steps (research → script → vocab → digest), then STOP and report.
              Do not fabricate audio and do not publish.
    exit 1  — hard failure (unparseable ledger, malformed data files): STOP and
              report before burning any tokens.

Checks (live calls verify credentials without printing them — presence and HTTP
status only, never values):
  - GEMINI_API_KEY present + accepted, and GEMINI_TTS_MODEL actually exists
    (preview models get retired; a 404 here means "pick a current TTS model")
  - R2 creds authenticate and R2_BUCKET exists (HeadBucket)
  - AUDIO_BASE_URL set (without it the MP3 would be committed to git)
  - FMP_API_KEY present + accepted (WARN only — markets can be hand-written
    from the brief, but never from memory)
  - ffmpeg reachable (PATH or imageio_ffmpeg) and boto3 importable
  - free disk ≥ ~1.5 GB (a full render writes ~300 MB of PCM/WAV/MP3)
  - data/history.jsonl parses (a broken ledger silently blinds dedup)
  - today's episode not already on origin/<DEPLOY_BRANCH> (double-run notice)

Env:
    DEPLOY_BRANCH       default main
    GEMINI_TTS_MODEL    default matches render_gemini.py
    SKIP_LIVE_CHECKS=1  offline mode — presence/parse checks only
"""
import datetime, json, os, shutil, subprocess, sys, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL_HARD, FAIL_AUDIO, WARN = [], [], []


def ok(msg):
    print(f"  ✓ {msg}")


def warn(msg):
    WARN.append(msg)
    print(f"  ⚠ {msg}")


def fail(msg, audio_side=False):
    (FAIL_AUDIO if audio_side else FAIL_HARD).append(msg)
    print(f"  ✗ {msg}")


def http_status(url, timeout=20):
    """GET a URL, return (status, None) or (None, error-string). Secrets stay in
    the URL and are never printed."""
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url), timeout=timeout) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return None, type(e).__name__


def check_deps():
    print("deps:")
    try:
        import boto3  # noqa: F401
        ok("boto3 importable")
    except ImportError:
        fail("boto3 missing — pip install -r tools/requirements.txt (R2 upload/prune will fail)",
             audio_side=True)
    ff = shutil.which("ffmpeg")
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    if ff:
        ok("ffmpeg reachable")
    else:
        fail("no ffmpeg (PATH or imageio_ffmpeg) — render would produce WAV only, "
             "publish needs the MP3; pip install imageio-ffmpeg", audio_side=True)


def check_disk():
    print("disk:")
    free = shutil.disk_usage(ROOT).free
    gb = free / 1e9
    if gb < 1.5:
        fail(f"only {gb:.1f} GB free — a render writes ~300 MB and git needs room; "
             "delete old WAV/PCM leftovers first", audio_side=True)
    elif gb < 4:
        warn(f"{gb:.1f} GB free — enough, but tight; consider cleaning render leftovers")
    else:
        ok(f"{gb:.0f} GB free")


def check_gemini(live):
    print("gemini (TTS):")
    key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    if not key:
        fail("GEMINI_API_KEY not set — no audio possible", audio_side=True)
        return
    ok("GEMINI_API_KEY present")
    if not live:
        return
    status, err = http_status(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}?key={key}")
    if status == 200:
        ok(f"key accepted; model '{model}' exists")
    elif status in (400, 401, 403):
        fail(f"Gemini rejected the key (HTTP {status}) — rotate/fix GEMINI_API_KEY",
             audio_side=True)
    elif status == 404:
        fail(f"TTS model '{model}' not found (HTTP 404) — it was likely retired; "
             "set GEMINI_TTS_MODEL to a current TTS model", audio_side=True)
    elif status is not None:
        warn(f"Gemini check inconclusive (HTTP {status}) — proceed, but the render may fail")
    else:
        warn(f"Gemini unreachable ({err}) — network/proxy issue; proceed with caution")


def check_r2(live):
    print("r2 (audio storage):")
    need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        fail("missing env: " + ", ".join(missing) + " — upload/retention will fail",
             audio_side=True)
    else:
        ok("all four R2 vars present")
    base = os.environ.get("AUDIO_BASE_URL", "")
    if not base:
        fail("AUDIO_BASE_URL not set — daily.sh would fall back to committing the "
             "MP3 into git (dev mode); set the public audio base", audio_side=True)
    elif not base.startswith("https://"):
        warn(f"AUDIO_BASE_URL doesn't start with https:// — double-check it")
    else:
        ok("AUDIO_BASE_URL set")
    if missing or not live:
        return
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError
    except ImportError:
        return  # already failed in check_deps
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(connect_timeout=15, read_timeout=20, retries={"max_attempts": 1}),
    )
    bucket = os.environ["R2_BUCKET"]
    try:
        s3.head_bucket(Bucket=bucket)
        ok(f"R2 credentials accepted; bucket '{bucket}' exists")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket"):
            fail(f"R2 bucket '{bucket}' not found — R2_BUCKET is wrong "
                 "(check the exact bucket name in the Cloudflare dashboard)",
                 audio_side=True)
        elif code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            fail(f"R2 rejected the credentials ({code}) — fix the R2 keys", audio_side=True)
        else:
            warn(f"R2 check inconclusive ({code or 'unknown error'}) — upload may still fail")
    except Exception as e:
        warn(f"R2 unreachable ({type(e).__name__}) — network/proxy issue")


def check_fmp(live):
    print("fmp (markets data):")
    key = os.environ.get("FMP_API_KEY")
    if not key:
        warn("FMP_API_KEY not set — market_snapshot.py won't run; hand-write "
             "routine/markets-<date>.json from real numbers in the brief (NEVER from memory)")
        return
    ok("FMP_API_KEY present")
    if not live:
        return
    status, err = http_status(
        f"https://financialmodelingprep.com/stable/quote-short?symbol=SPY&apikey={key}")
    if status == 200:
        ok("key accepted")
    elif status in (401, 403):
        warn(f"FMP rejected the key (HTTP {status}) — markets fall back to hand-written "
             "numbers from the brief")
    elif status == 429:
        warn("FMP rate-limited right now (429) — key works but pace the calls")
    elif status is not None:
        warn(f"FMP check inconclusive (HTTP {status})")
    else:
        warn(f"FMP unreachable ({err})")


def check_ledger():
    print("ledger (dedup memory):")
    path = os.path.join(ROOT, "data", "history.jsonl")
    if not os.path.isfile(path):
        fail("data/history.jsonl missing — dedup would run blind; are you on the "
             "deploy branch after `git pull`?")
        return
    good = bad = 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            json.loads(line)
            good += 1
        except json.JSONDecodeError:
            bad += 1
    if good == 0:
        fail("data/history.jsonl has no parseable entries — dedup would run blind")
    elif bad:
        warn(f"ledger: {bad} corrupt line(s) out of {good + bad} — those episodes are "
             "invisible to dedup; a rebuild (build_episode.py) self-heals it")
    else:
        ok(f"{good} episodes on ledger")


def check_double_run():
    print("publish state:")
    branch = os.environ.get("DEPLOY_BRANCH", "main")
    today = datetime.date.today().isoformat()
    raw = subprocess.run(
        ["git", "show", f"origin/{branch}:data/index.json"],
        capture_output=True, text=True, cwd=ROOT).stdout
    try:
        idx = json.loads(raw)
    except json.JSONDecodeError:
        warn(f"couldn't read origin/{branch}:data/index.json — fetch the deploy branch first")
        return
    if any(e.get("date") == today for e in idx.get("episodes", [])):
        warn(f"episode {today} is ALREADY published on origin/{branch} — a re-run "
             "will no-op at push; only proceed if you intend to replace today's show")
    else:
        ok(f"no {today} episode upstream yet")


def main():
    live = os.environ.get("SKIP_LIVE_CHECKS") != "1"
    print(f"preflight — {datetime.date.today().isoformat()}"
          + ("" if live else "  (offline: presence checks only)"))
    check_deps()
    check_disk()
    check_gemini(live)
    check_r2(live)
    check_fmp(live)
    check_ledger()
    check_double_run()

    print()
    if FAIL_HARD:
        print(f"✗ PREFLIGHT FAILED ({len(FAIL_HARD)} hard): stop and report — "
              "do not start the run.", file=sys.stderr)
        sys.exit(1)
    if FAIL_AUDIO:
        print(f"✗ AUDIO-SIDE FAILURE ({len(FAIL_AUDIO)}): do the TEXT steps "
              "(brief → script → vocab → digest), then STOP and report — no render, "
              "no publish, no fabricated audio.", file=sys.stderr)
        sys.exit(3)
    print(f"✓ preflight clear" + (f" ({len(WARN)} warning(s) above)" if WARN else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
