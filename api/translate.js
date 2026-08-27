// The Morning Commute — Mandarin tap-to-translate (Vercel serverless function).
//
// The transcript's Mandarin lines carry a 「译」 button; tapping it posts the
// sentence here and gets back a full translation plus a word-by-word breakdown
// (characters / pinyin / gloss) for EVERY word, not just the day's vocab. Same
// proxy pattern as api/chat.js so the API key never ships to the client, and the
// app caches results in localStorage so each sentence is translated at most once
// per device. Configure in the Vercel project:
//   ANTHROPIC_API_KEY  (required)  — shared with the vocab chat
//   TRANSLATE_MODEL    (optional)  — defaults to CHAT_MODEL, then claude-sonnet-5

const DEFAULT_MODEL = 'claude-sonnet-5';

const SYSTEM = `You are a Mandarin-to-English annotation service for a language learner (HSK 4). Given one Mandarin sentence (it may contain some English), reply with ONLY a JSON object — no markdown fences, no commentary — in exactly this shape:
{"translation":"natural English translation of the full sentence","words":[{"zh":"词","pinyin":"cí","gloss":"short English meaning"}]}
Rules: segment the Mandarin into words/phrases the way a learner's dictionary would (multi-character words stay together, e.g. 房地产 / 央行 / 货币政策); include EVERY Mandarin word in reading order; use tone-marked pinyin; keep each gloss to a few words, matched to this sentence's usage; skip punctuation and any English spans (they need no entry).`;

function readBody(req) {
  return new Promise(resolve => {
    if (req.body != null) {
      if (typeof req.body === 'string') { try { return resolve(JSON.parse(req.body)); } catch { return resolve({}); } }
      return resolve(req.body);
    }
    let data = '';
    req.on('data', c => { data += c; });
    req.on('end', () => { try { resolve(JSON.parse(data || '{}')); } catch { resolve({}); } });
    req.on('error', () => resolve({}));
  });
}

module.exports = async (req, res) => {
  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'POST') { res.status(405).json({ error: 'Method not allowed.' }); return; }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    res.status(200).json({ error: "Translation isn't set up yet. Add an ANTHROPIC_API_KEY in the Vercel project settings to enable it." });
    return;
  }

  try {
    const { text = '' } = await readBody(req);
    const sentence = String(text).trim().slice(0, 1000);
    if (!sentence || !/[一-鿿]/.test(sentence)) {
      res.status(200).json({ error: 'No Mandarin text to translate.' });
      return;
    }

    const upstream = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: process.env.TRANSLATE_MODEL || process.env.CHAT_MODEL || DEFAULT_MODEL,
        max_tokens: 1500,
        system: SYSTEM,
        messages: [{ role: 'user', content: sentence }],
      }),
    });

    const data = await upstream.json().catch(() => null);
    if (!upstream.ok) {
      const msg = (data && data.error && data.error.message) || `Upstream error ${upstream.status}.`;
      res.status(200).json({ error: msg });
      return;
    }
    const raw = Array.isArray(data && data.content)
      ? data.content.filter(b => b.type === 'text').map(b => b.text).join('').trim()
      : '';
    // strict-JSON is requested, but strip fences defensively before parsing
    const jsonText = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
    let parsed;
    try { parsed = JSON.parse(jsonText); } catch {
      res.status(200).json({ error: 'Translation service returned an unexpected format — try again.' });
      return;
    }
    const words = Array.isArray(parsed.words)
      ? parsed.words
          .filter(w => w && typeof w.zh === 'string' && w.zh)
          .map(w => ({ zh: String(w.zh), pinyin: String(w.pinyin || ''), gloss: String(w.gloss || '') }))
      : [];
    res.status(200).json({ translation: String(parsed.translation || ''), words });
  } catch (e) {
    res.status(200).json({ error: 'Translation failed: ' + (e && e.message ? e.message : String(e)) });
  }
};
