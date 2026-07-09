// The Morning Commute — vocab tutor chatbot (Vercel serverless function).
//
// Proxies the browser to the Anthropic Messages API so the API key never ships to
// the client. Configure it in the Vercel project:
//   ANTHROPIC_API_KEY  (required)  — your Anthropic API key
//   CHAT_MODEL         (optional)  — model id, defaults to claude-sonnet-5
//
// If the key is missing (e.g. on static hosting without env vars), it returns a
// friendly { error } that the UI shows in place of a reply — nothing crashes.

const DEFAULT_MODEL = 'claude-sonnet-5';

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

function buildSystem(deck, card) {
  const deckLines = (Array.isArray(deck) ? deck : []).slice(0, 60)
    .map(c => `- [${c.lang}] ${c.word}${c.pinyin ? ` (${c.pinyin})` : ''} — ${c.meaning}`)
    .join('\n');

  const focus = card ? `

The learner is currently looking at this card, so default to it when they say "this word":
Word: ${card.word}${card.pinyin ? ` (${card.pinyin})` : ''} [${card.lang}]
Meaning: ${card.meaning}` +
    (card.example ? `\nExample: ${card.example}${card.exampleMeaning ? ` — ${card.exampleMeaning}` : ''}` : '') +
    (card.note ? `\nNote: ${card.note}` : '') : '';

  return `You are a warm, precise language tutor for a learner studying Mandarin Chinese and Tagalog vocabulary drawn from a daily news podcast called "The Morning Commute."

Help them understand and remember the words. Be concise and mobile-friendly: short paragraphs, a few sentences at most unless they ask for more. When it helps, give a fresh example sentence with pinyin (Mandarin) or a pronunciation hint (Tagalog) plus an English gloss. Explain tone, register, and how near-synonyms differ. Use the learner's own cards below as shared context when relevant; if they ask about a word that isn't in the deck, still help. Answer in English unless asked otherwise. Use light Markdown (**bold**, \`code\`) only.

The learner's current vocabulary deck:
${deckLines || '(none provided)'}${focus}`;
}

module.exports = async (req, res) => {
  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'POST') { res.status(405).json({ error: 'Method not allowed.' }); return; }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    res.status(200).json({ error: "Chat isn't set up yet. Add an ANTHROPIC_API_KEY in the Vercel project settings to enable it." });
    return;
  }

  try {
    const { messages = [], card = null, deck = [] } = await readBody(req);
    const clean = (Array.isArray(messages) ? messages : [])
      .filter(m => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string' && m.content.trim())
      .slice(-12)
      .map(m => ({ role: m.role, content: m.content.slice(0, 4000) }));
    if (!clean.length) { res.status(200).json({ error: 'Empty message.' }); return; }
    if (clean[clean.length - 1].role !== 'user') { res.status(200).json({ error: 'Last message must be from the user.' }); return; }

    const upstream = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: process.env.CHAT_MODEL || DEFAULT_MODEL,
        max_tokens: 700,
        system: buildSystem(deck, card),
        messages: clean,
      }),
    });

    const data = await upstream.json().catch(() => null);
    if (!upstream.ok) {
      const msg = (data && data.error && data.error.message) || `Upstream error ${upstream.status}.`;
      res.status(200).json({ error: msg });
      return;
    }
    const reply = Array.isArray(data && data.content)
      ? data.content.filter(b => b.type === 'text').map(b => b.text).join('').trim()
      : '';
    res.status(200).json({ reply: reply || '(no response)' });
  } catch (e) {
    res.status(200).json({ error: 'Chat failed: ' + (e && e.message ? e.message : String(e)) });
  }
};
