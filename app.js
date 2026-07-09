'use strict';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const DATA = 'data/';
const DAY = 86400000;
const SRS_DAYS = [0, 1, 3, 7, 21]; // Leitner box -> days until due

const audio = new Audio();
audio.preload = 'metadata';
const AUDIO_CACHE = 'commute-runtime-v2';   // must match RUNTIME in sw.js
let INDEX = null, CUR = null, DECK = null, SEARCH = null;

// ---------- persisted state ----------
const KEY = 'commute.v1';
function loadState() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; }
}
function saveState() { localStorage.setItem(KEY, JSON.stringify(S)); }
const S = Object.assign({ tab: 'listen', speed: 1.5, srs: {}, pos: {}, epDate: null }, loadState());

const fmtTime = s => {
  if (!isFinite(s)) return '0:00';
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60); return `${m}:${String(s % 60).padStart(2, '0')}`;
};
const todayDay = () => Math.floor(Date.now() / DAY);
async function getJSON(u) { const r = await fetch(u, { cache: 'no-cache' }); if (!r.ok) throw new Error(u); return r.json(); }

function toast(msg) {
  let t = $('.toast'); if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.append(t); }
  t.textContent = msg; t.classList.add('show'); clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), 1600);
}

// ---------- routing ----------
function setTab(tab) {
  S.tab = tab; saveState();
  $$('.tabbar button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  ({ listen: viewListen, vocab: viewVocab, search: viewSearch, archive: viewArchive }[tab])();
}
$$('.tabbar button').forEach(b => b.onclick = () => setTab(b.dataset.tab));

// ================= LISTEN =================
async function loadEpisode(date) {
  CUR = await getJSON(`${DATA}episodes/${date}/episode.json`);
  S.epDate = date; saveState();
}

async function viewListen() {
  const view = $('#view');
  if (!INDEX) INDEX = await getJSON(`${DATA}index.json`);
  const date = S.epDate && INDEX.episodes.find(e => e.date === S.epDate)
    ? S.epDate : (INDEX.episodes[0] && INDEX.episodes[0].date);
  if (!date) { view.innerHTML = `<div class="empty">No episodes yet.</div>`; return; }
  if (!CUR || CUR.date !== date) await loadEpisode(date);

  $('#ep-title').textContent = 'The Morning Commute';
  $('#ep-sub').textContent = CUR.title || CUR.date;

  // `audio` is a full URL when served from a bucket/CDN (R2), or a bare filename
  // for episodes that still keep the MP3 in the repo.
  const audioUrl = CUR.audio
    ? (/^https?:\/\//.test(CUR.audio) ? CUR.audio : `${DATA}episodes/${date}/${CUR.audio}`)
    : null;
  view.innerHTML = `
    <section class="card player">
      <div class="ttl">${CUR.title || CUR.date}</div>
      <div class="muted small">${CUR.segments.length} segments · ~${Math.round((CUR.durationSec||0)/60)} min</div>
      ${audioUrl ? `
      <div class="controls">
        <button class="play" id="play">▶</button>
        <div style="flex:1">
          <div class="scrub">
            <span class="time" id="cur">0:00</span>
            <input type="range" id="seek" min="0" max="1000" value="0">
            <span class="time" id="dur">${fmtTime(CUR.durationSec)}</span>
          </div>
          <div class="speeds" id="speeds"></div>
        </div>
      </div>
      <div class="offline-row">
        <button class="iconbtn" id="saveoff">⤓ Save audio for offline</button>
        <span class="muted small" id="saveoff-state"></span>
      </div>` : `<div class="muted small" style="margin-top:8px">Audio not available for this episode — script only.</div>`}
      <div class="chips" id="chips" style="margin-top:12px"></div>
      ${audioUrl ? `<div class="approx">Segment jumps are approximate (estimated from script length).</div>` : ``}
    </section>
    <div id="script"></div>`;

  // chips
  const chips = $('#chips');
  CUR.segments.forEach((sg, i) => {
    const c = document.createElement('button'); c.className = 'chip'; c.textContent = sg.label;
    c.onclick = () => {
      if (audioUrl && isFinite(sg.startSec)) audio.currentTime = sg.startSec;
      $(`#seg-${i}`).scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    chips.append(c);
  });

  // transcript
  $('#script').innerHTML = CUR.segments.map((sg, i) => `
    <section class="seg" id="seg-${i}">
      <h3>${sg.label}</h3>
      ${sg.turns.map(t => {
        const who = t.speaker === 'ALEX' ? 'alex' : 'sam';
        const name = t.speaker === 'ALEX' ? 'ALEX' : 'SAM';
        return `<div class="turn ${who}"><div class="who">${name}</div><div class="txt">${t.text}</div></div>`;
      }).join('')}
    </section>`).join('');

  if (audioUrl) setupPlayer(audioUrl, date);
}

function setupPlayer(url, date) {
  if (audio.dataset.url !== url) {
    audio.src = url; audio.dataset.url = url;
    const saved = S.pos[date]; if (saved) audio.currentTime = saved;
  }
  audio.playbackRate = S.speed;

  const play = $('#play'), seek = $('#seek'), cur = $('#cur'), dur = $('#dur');
  const speeds = $('#speeds');
  [1, 1.25, 1.5, 1.75, 2].forEach(r => {
    const b = document.createElement('button'); b.textContent = r + '×';
    b.className = r === S.speed ? 'on' : '';
    b.onclick = () => { S.speed = r; audio.playbackRate = r; saveState();
      $$('#speeds button').forEach(x => x.classList.toggle('on', x === b)); };
    speeds.append(b);
  });

  const sync = () => { play.textContent = audio.paused ? '▶' : '❚❚'; };
  play.onclick = () => { audio.paused ? audio.play() : audio.pause(); };
  audio.onplay = audio.onpause = sync; sync();

  let seeking = false;
  seek.oninput = () => { seeking = true; cur.textContent = fmtTime(seek.value / 1000 * (audio.duration || CUR.durationSec)); };
  seek.onchange = () => { audio.currentTime = seek.value / 1000 * (audio.duration || CUR.durationSec); seeking = false; };

  audio.onloadedmetadata = () => { dur.textContent = fmtTime(audio.duration); };
  audio.ontimeupdate = () => {
    const d = audio.duration || CUR.durationSec || 1;
    if (!seeking) { seek.value = Math.round(audio.currentTime / d * 1000); cur.textContent = fmtTime(audio.currentTime); }
    S.pos[date] = audio.currentTime;            // resume point
    if ((audio.currentTime | 0) % 5 === 0) saveState();
    // highlight active segment
    let act = 0;
    CUR.segments.forEach((sg, i) => { if (isFinite(sg.startSec) && audio.currentTime >= sg.startSec) act = i; });
    $$('#script .seg').forEach((el, i) => el.classList.toggle('active', i === act));
    $$('#chips .chip').forEach((el, i) => el.classList.toggle('on', i === act));
  };

  wireSaveOffline(url);

  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: CUR.title || 'The Morning Commute', artist: 'The Morning Commute',
      album: 'Daily', artwork: [{ src: 'icon-512.png', sizes: '512x512', type: 'image/png' }],
    });
    navigator.mediaSession.setActionHandler('play', () => audio.play());
    navigator.mediaSession.setActionHandler('pause', () => audio.pause());
    navigator.mediaSession.setActionHandler('seekbackward', () => audio.currentTime -= 15);
    navigator.mediaSession.setActionHandler('seekforward', () => audio.currentTime += 30);
  }
}

// Save the full MP3 into the cache so it plays with no signal. Cross-origin range
// (206) responses can't be cached by the SW, so we fetch the whole file (200) once
// here; the SW then serves it cache-first (see sw.js).
async function wireSaveOffline(url) {
  const btn = $('#saveoff'), state = $('#saveoff-state');
  if (!btn || !('caches' in window)) { if (btn) btn.style.display = 'none'; return; }
  const cache = await caches.open(AUDIO_CACHE);
  const cached = await cache.match(url, { ignoreVary: true });
  const done = () => { btn.style.display = 'none'; state.textContent = '✓ Saved for offline'; };
  if (cached) { done(); return; }
  btn.onclick = async () => {
    btn.disabled = true; state.textContent = 'Saving…';
    try {
      const res = await fetch(url, { mode: 'cors' });
      if (!res.ok) throw new Error(res.status);
      await cache.put(url, res.clone());
      done(); toast('Saved for offline');
    } catch (e) {
      btn.disabled = false; state.textContent = '';
      toast('Could not save (check connection / CORS)');
    }
  };
}

// ================= SEARCH =================
function snippet(text, q) {
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text.slice(0, 140) + '…';
  const a = Math.max(0, i - 60), b = Math.min(text.length, i + q.length + 80);
  const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  return (a > 0 ? '…' : '') + esc(text.slice(a, i)) +
    '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>' +
    esc(text.slice(i + q.length, b)) + (b < text.length ? '…' : '');
}

async function viewSearch() {
  const view = $('#view'); $('#ep-sub').textContent = '';
  if (!SEARCH) { try { SEARCH = (await getJSON(`${DATA}search.json`)).docs; } catch { SEARCH = []; } }
  view.innerHTML = `
    <div class="searchbar"><input type="search" id="q" placeholder="Search every episode…" autocomplete="off"></div>
    <div id="results" class="muted small" style="padding:4px 2px">${SEARCH.length} episode${SEARCH.length === 1 ? '' : 's'} indexed.</div>`;
  const q = $('#q'), results = $('#results');
  const run = () => {
    const terms = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { results.className = 'muted small'; results.style.padding = '4px 2px';
      results.innerHTML = `${SEARCH.length} episode${SEARCH.length === 1 ? '' : 's'} indexed.`; return; }
    const hits = SEARCH.filter(d => { const t = d.text.toLowerCase(); return terms.every(w => t.includes(w)); });
    results.className = ''; results.style.padding = '0';
    if (!hits.length) { results.innerHTML = `<div class="empty">No matches for “${q.value}”.</div>`; return; }
    results.innerHTML = hits.map(d => `
      <section class="card ep result" data-date="${d.date}">
        <div class="meta">
          <div class="t">${d.title || d.date}</div>
          <div class="muted small snip">${snippet(d.text, terms[0])}</div>
        </div>
        <div class="muted">›</div>
      </section>`).join('');
    $$('.result').forEach(el => el.onclick = async () => { await loadEpisode(el.dataset.date); setTab('listen'); });
  };
  q.oninput = run; q.focus();
}

// ================= VOCAB =================
// A reference + learning surface: browse the whole archive as flippable cards
// (with SRS review) or as a scannable list, search across everything, and ask a
// tutor chatbot follow-up questions about any word.
async function buildDeck() {
  if (!INDEX) INDEX = await getJSON(`${DATA}index.json`);
  const cards = [];
  for (const e of INDEX.episodes) {            // INDEX is newest-first → DECK is too
    if (!e.vocabCount) continue;
    try {
      const v = await getJSON(`${DATA}episodes/${e.date}/vocab.json`);
      v.cards.forEach(c => cards.push(Object.assign({ date: e.date }, c)));
    } catch {}
  }
  DECK = cards;
}

const escHTML = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

// ---- vocab state ----
let vMode = (S.vMode === 'list' ? 'list' : 'cards');   // 'cards' | 'list'
let vScope = 'all';                                    // 'all' | 'due'  (cards mode)
let vFilter = ['Mandarin', 'Tagalog'].includes(S.vFilter) ? S.vFilter : 'All';
let vSearch = '';
let vQueue = [], vIdx = 0, vFlipped = false;

function cardHay(c) {
  return [c.word, c.pinyin, c.pronunciation, c.meaning, c.example,
          c.examplePinyin, c.exampleMeaning, c.note, c.tiesTo, c.lang, c.date]
    .filter(Boolean).join(' ').toLowerCase();
}
function matchCard(c) {
  const terms = vSearch.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const hay = cardHay(c);
  return terms.every(w => hay.includes(w));
}
// Cards passing the current language filter + search. `forReview` also keeps only
// SRS-due cards, soonest first — the Cards-mode "Due" queue.
function currentCards(forReview) {
  let cards = DECK.filter(c => (vFilter === 'All' || c.lang === vFilter) && matchCard(c));
  if (forReview) {
    const t = todayDay();
    cards = cards.filter(c => (S.srs[c.id]?.due ?? 0) <= t)
                 .sort((a, b) => (S.srs[a.id]?.due ?? 0) - (S.srs[b.id]?.due ?? 0));
  }
  return cards;
}
// Recompute the flashcard queue. Called only on structural changes (mode/filter/
// scope/search) — never on plain nav/grade, so grading never yanks a card out of
// the session you're mid-way through.
function refreshQueue() {
  vQueue = currentCards(vScope === 'due');
  if (vIdx >= vQueue.length) vIdx = 0;
  vFlipped = false;
}

async function viewVocab() {
  const view = $('#view');
  $('#ep-sub').textContent = '';
  if (!DECK) { view.innerHTML = `<div class="empty">Loading vocab…</div>`; await buildDeck(); }
  view.innerHTML = `<div id="v-controls"></div><div id="v-body"></div><div id="v-chat"></div>`;
  refreshQueue();
  renderVocabControls();
  renderVocabBody();
  renderChat();
}

// The controls (mode toggle, search, language filter, scope) render once and stay
// put; only the body re-renders while you type so the search input keeps focus.
function renderVocabControls() {
  const el = $('#v-controls');
  const modes = [['cards', 'Cards'], ['list', 'List']];
  const langs = ['All', 'Mandarin', 'Tagalog'];
  el.innerHTML = `
    <div class="deckhead">
      <div class="seg-filter mode">${modes.map(([k, l]) =>
        `<button class="${k === vMode ? 'on' : ''}" data-m="${k}">${l}</button>`).join('')}</div>
      <span class="spacer"></span>
      <span class="pill" id="v-count"></span>
    </div>
    <div class="searchbar vocab-search">
      <input type="search" id="v-q" placeholder="Search words, meanings, notes…" autocomplete="off" value="${escHTML(vSearch)}">
    </div>
    <div class="deckhead">
      <div class="seg-filter lang">${langs.map(l =>
        `<button class="${l === vFilter ? 'on' : ''}" data-l="${l}">${l}</button>`).join('')}</div>
      ${vMode === 'cards' ? `<span class="spacer"></span>
      <div class="seg-filter scope">${[['all', 'All'], ['due', 'Due']].map(([k, l]) =>
        `<button class="${k === vScope ? 'on' : ''}" data-s="${k}">${l}</button>`).join('')}</div>` : ``}
    </div>`;

  $$('.seg-filter.mode button', el).forEach(b => b.onclick = () => {
    vMode = b.dataset.m; S.vMode = vMode; saveState(); vIdx = 0;
    refreshQueue(); renderVocabControls(); renderVocabBody();
  });
  $$('.seg-filter.lang button', el).forEach(b => b.onclick = () => {
    vFilter = b.dataset.l; S.vFilter = vFilter; saveState(); vIdx = 0;
    refreshQueue(); renderVocabControls(); renderVocabBody();
  });
  $$('.seg-filter.scope button', el).forEach(b => b.onclick = () => {
    vScope = b.dataset.s; vIdx = 0; refreshQueue(); renderVocabControls(); renderVocabBody();
  });
  const q = $('#v-q');
  q.oninput = () => { vSearch = q.value; vIdx = 0; refreshQueue(); renderVocabBody(); };
}

function setCount(shown) {
  const el = $('#v-count'); if (el) el.textContent = `${shown} / ${DECK.length}`;
}

function renderVocabBody() {
  const body = $('#v-body');
  if (vMode === 'list') renderList(body);
  else renderCards(body);
}

// ---- list / reference mode ----
function renderList(body) {
  const cards = currentCards(false);
  setCount(cards.length);
  if (!cards.length) {
    body.innerHTML = `<div class="card empty">${
      vSearch ? `No cards match “${escHTML(vSearch)}”.` : `No vocab cards yet.`}</div>`;
    return;
  }
  body.innerHTML = `<div class="vlist">` + cards.map((c, i) => `
    <div class="vrow" data-i="${i}">
      <button class="vrow-head">
        <div class="vrow-main">
          <span class="vword">${escHTML(c.word)}</span>
          <span class="vroman">${escHTML(c.pinyin || c.pronunciation || '')}</span>
        </div>
        <span class="pill lang-${c.lang}">${escHTML(c.lang)}</span>
        <span class="vchev">›</span>
      </button>
      <div class="vrow-meaning">${escHTML(c.meaning)}</div>
      <div class="vrow-detail">
        ${c.example ? `<div class="ex">
          <div class="o">${escHTML(c.example)}</div>
          ${c.examplePinyin ? `<div class="p">${escHTML(c.examplePinyin)}</div>` : ''}
          ${c.exampleMeaning ? `<div class="m">${escHTML(c.exampleMeaning)}</div>` : ''}
        </div>` : ''}
        ${c.note ? `<div class="note">${escHTML(c.note)}</div>` : ''}
        <div class="vrow-foot">
          <span class="muted small">${escHTML(c.date)}${c.tiesTo ? ' · ' + escHTML(c.tiesTo) : ''}</span>
          <span class="spacer"></span>
          <button class="speak vrow-speak" data-i="${i}">🔊</button>
          <button class="linkbtn vrow-ask" data-i="${i}">Ask ›</button>
        </div>
      </div>
    </div>`).join('') + `</div>`;

  $$('.vrow', body).forEach(r => {
    r.querySelector('.vrow-head').onclick = () => r.classList.toggle('open');
  });
  $$('.vrow-speak', body).forEach(b => b.onclick = e => { e.stopPropagation(); speak(cards[+b.dataset.i]); });
  $$('.vrow-ask', body).forEach(b => b.onclick = e => { e.stopPropagation(); focusChatOn(cards[+b.dataset.i]); });
}

// ---- flashcard mode ----
function renderCards(body) {
  setCount(vQueue.length);
  if (!vQueue.length) {
    body.innerHTML = `<div class="card empty">${
      vSearch ? `No cards match “${escHTML(vSearch)}”.`
      : vScope === 'due' ? `✓ Nothing due right now. Switch to <b>All</b> to browse everything.`
      : `No vocab cards yet.`}</div>`;
    return;
  }
  if (vIdx >= vQueue.length) vIdx = vQueue.length - 1;
  const card = vQueue[vIdx];
  body.innerHTML = `
    <div class="progress">${vIdx + 1} / ${vQueue.length}${vScope === 'due' ? ' due' : ''}${vFilter !== 'All' ? ' · ' + vFilter : ''} · ${escHTML(card.date)}</div>
    <div class="flash ${vFlipped ? 'flipped' : ''}" id="flash">
      <div class="inner">
        <div class="face front">
          <span class="lang-tag pill">${escHTML(card.lang)}</span>
          <div class="word">${escHTML(card.word)}</div>
          <div class="roman">${escHTML(card.pinyin || card.pronunciation || '')}</div>
          ${card.lang === 'Mandarin' && card.tones ? `<div class="tones">${escHTML(card.tones)}</div>` : ''}
          <div class="tap-hint">tap to flip
            <button class="speak" id="speak">🔊 say it</button></div>
        </div>
        <div class="face back">
          <span class="lang-tag pill">${escHTML(card.lang)}${card.tiesTo ? ' · ' + escHTML(card.tiesTo) : ''}</span>
          <div class="meaning">${escHTML(card.meaning)}</div>
          <div class="ex">
            <div class="o">${escHTML(card.example || '')}</div>
            ${card.examplePinyin ? `<div class="p">${escHTML(card.examplePinyin)}</div>` : ''}
            ${card.exampleMeaning ? `<div class="m">${escHTML(card.exampleMeaning)}</div>` : ''}
          </div>
          ${card.note ? `<div class="note">${escHTML(card.note)}</div>` : ''}
          <button class="linkbtn card-ask" id="card-ask">Ask about this word ›</button>
          <div class="tap-hint">tap to flip back</div>
        </div>
      </div>
    </div>
    <div class="deck-nav">
      <button class="iconbtn" id="prev" ${vIdx === 0 ? 'disabled' : ''}>‹ Prev</button>
      <button class="iconbtn" id="next" ${vIdx >= vQueue.length - 1 ? 'disabled' : ''}>Next ›</button>
    </div>
    ${vScope === 'due' ? `<div class="deck-actions">
      <button class="btn-review" id="again">Review again</button>
      <button class="btn-know" id="know">Got it</button>
    </div>` : ``}`;

  $('#flash').onclick = e => {
    if (e.target.closest('#speak') || e.target.closest('#card-ask')) return;
    vFlipped = !vFlipped; $('#flash').classList.toggle('flipped');
  };
  const sp = $('#speak'); if (sp) sp.onclick = e => { e.stopPropagation(); speak(card); };
  const ask = $('#card-ask'); if (ask) ask.onclick = e => { e.stopPropagation(); focusChatOn(card); };
  const go = d => { vIdx = Math.min(Math.max(vIdx + d, 0), vQueue.length - 1); vFlipped = false; renderVocabBody(); };
  $('#prev').onclick = () => go(-1);
  $('#next').onclick = () => go(1);
  if (vScope === 'due') {
    $('#again').onclick = () => grade(card, false);
    $('#know').onclick = () => grade(card, true);
  }
}

// Records the SRS schedule for the next day but never removes the card from the
// current session — you can keep flipping through everything you just reviewed.
function grade(card, known) {
  const t = todayDay();
  const cur = S.srs[card.id] || { box: 0, due: 0 };
  const box = known ? Math.min(cur.box + 1, SRS_DAYS.length - 1) : 0;
  S.srs[card.id] = { box, due: t + SRS_DAYS[box] };
  saveState();
  toast(known ? 'Got it' : 'Will resurface');
  if (vIdx < vQueue.length - 1) { vIdx++; vFlipped = false; renderVocabBody(); }
}

function speak(card) {
  if (!('speechSynthesis' in window)) { toast('Speech not supported'); return; }
  const u = new SpeechSynthesisUtterance(card.word);
  u.lang = card.lang === 'Mandarin' ? 'zh-CN' : 'fil-PH';
  u.rate = card.lang === 'Mandarin' ? 0.75 : 0.9;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

// ================= VOCAB CHAT =================
// A tutor chatbot for follow-up questions. Talks to /api/chat (a serverless
// function that proxies Anthropic). Degrades gracefully to a clear message when
// the endpoint isn't deployed (e.g. static hosting) or has no API key.
let chatMsgs = Array.isArray(S.chat) ? S.chat.slice(-20) : []; // {role:'user'|'assistant'|'error', text}
let chatCard = null;   // card the next question is "about", shown as a context chip
let chatBusy = false;

function mdLite(t) {
  return escHTML(t)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function renderChat() {
  const el = $('#v-chat'); if (!el) return;
  const open = S.chatOpen !== false;
  el.innerHTML = `
    <div class="chatwrap ${open ? '' : 'collapsed'}" id="chatwrap">
      <button class="chathead" id="chathead">
        <span>💬 Ask about the words</span>
        <span class="chattoggle">${open ? '▾' : '▸'}</span>
      </button>
      <div class="chatpanel">
        <div class="chatlog" id="chatlog"></div>
        <div class="chatctx" id="chatctx"></div>
        <div class="chatbar">
          <input id="chatq" placeholder="e.g. how is 一旦 different from 如果?" autocomplete="off">
          <button id="chatsend" aria-label="Send">➤</button>
        </div>
      </div>
    </div>`;

  $('#chathead').onclick = () => {
    const nowOpen = !(S.chatOpen !== false);
    S.chatOpen = nowOpen; saveState();
    $('#chatwrap').classList.toggle('collapsed', !nowOpen);
    $('#chathead .chattoggle').textContent = nowOpen ? '▾' : '▸';
  };
  $('#chatsend').onclick = submitChat;
  $('#chatq').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); submitChat(); } };
  paintChatLog();
  paintChatCtx();
}

function paintChatLog() {
  const log = $('#chatlog'); if (!log) return;
  if (!chatMsgs.length && !chatBusy) {
    log.innerHTML = `<div class="chat-empty muted small">Ask anything about these words — meanings, tone, register, how two near-synonyms differ, or ask for a fresh example sentence.</div>`;
    return;
  }
  log.innerHTML = chatMsgs.map(m => {
    const cls = m.role === 'assistant' ? 'assistant' : m.role === 'error' ? 'error' : 'user';
    const html = m.role === 'assistant' ? mdLite(m.text) : escHTML(m.text);
    return `<div class="msg ${cls}">${html}</div>`;
  }).join('') + (chatBusy
    ? `<div class="msg assistant thinking"><span class="dots"><i></i><i></i><i></i></span></div>` : '');
  log.scrollTop = log.scrollHeight;
}

function paintChatCtx() {
  const c = $('#chatctx'); if (!c) return;
  if (chatCard) {
    c.innerHTML = `<span class="ctxchip">Re: <b>${escHTML(chatCard.word)}</b> `
      + `${escHTML(chatCard.pinyin || chatCard.pronunciation || '')} <button id="ctxclear" aria-label="Clear">✕</button></span>`;
    $('#ctxclear').onclick = () => { chatCard = null; paintChatCtx(); };
  } else {
    c.innerHTML = '';
  }
}

// Open the chat, point it at a specific card, and focus the input.
function focusChatOn(card) {
  chatCard = card;
  S.chatOpen = true; saveState();
  const wrap = $('#chatwrap');
  if (wrap) {
    wrap.classList.remove('collapsed');
    $('#chathead .chattoggle').textContent = '▾';
    paintChatCtx();
    const q = $('#chatq');
    if (q) { q.focus(); wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  }
  toast('Ask about ' + card.word);
}

function pickCtx(c) {
  return {
    lang: c.lang, word: c.word, pinyin: c.pinyin || c.pronunciation || '', meaning: c.meaning,
    example: c.example || '', examplePinyin: c.examplePinyin || '',
    exampleMeaning: c.exampleMeaning || '', note: c.note || '', date: c.date,
  };
}
function persistChat() { chatMsgs = chatMsgs.slice(-20); S.chat = chatMsgs; saveState(); }

async function submitChat() {
  const q = $('#chatq'); if (!q) return;
  const text = q.value.trim();
  if (!text || chatBusy) return;
  q.value = '';
  chatMsgs.push({ role: 'user', text });
  persistChat();
  chatBusy = true; paintChatLog();
  try {
    const reply = await callChat();
    chatBusy = false;
    chatMsgs.push({ role: 'assistant', text: reply });
  } catch (e) {
    chatBusy = false;
    chatMsgs.push({ role: 'error', text: e.message || String(e) });
  }
  persistChat(); paintChatLog();
}

async function callChat() {
  const history = chatMsgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(-10)
    .map(m => ({ role: m.role, content: m.text }));
  const payload = {
    messages: history,
    card: chatCard ? pickCtx(chatCard) : null,
    deck: (DECK || []).map(pickCtx),
  };
  let r;
  try {
    r = await fetch('/api/chat', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
    });
  } catch {
    throw new Error('Can’t reach the chat service — check your connection.');
  }
  if (r.status === 404) throw new Error('Chat isn’t available on this deployment yet.');
  let data;
  try { data = await r.json(); } catch { throw new Error('Chat service returned an unexpected response.'); }
  if (!r.ok || data.error) throw new Error(data.error || `Chat error (${r.status}).`);
  return data.reply || '(no response)';
}

// ================= ARCHIVE =================
const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
async function viewArchive() {
  const view = $('#view'); $('#ep-sub').textContent = '';
  if (!INDEX) INDEX = await getJSON(`${DATA}index.json`);
  if (!INDEX.episodes.length) { view.innerHTML = `<div class="empty">No episodes archived yet.</div>`; return; }
  view.innerHTML = INDEX.episodes.map(e => {
    const [y, m, d] = e.date.split('-');
    return `<section class="card ep" data-date="${e.date}">
      <div class="cal"><div class="d">${+d}</div><div class="mo">${MONTHS[+m-1]}</div></div>
      <div class="meta">
        <div class="t">${e.title || e.date}</div>
        <div class="muted small">~${Math.round((e.durationSec||0)/60)} min · ${e.segmentCount||0} segments · ${e.vocabCount||0} vocab${e.hasAudio?'':' · no audio'}</div>
      </div>
      <div class="muted">›</div>
    </section>`;
  }).join('');
  $$('.ep').forEach(el => el.onclick = async () => {
    await loadEpisode(el.dataset.date); setTab('listen');
  });
}

// ---------- boot ----------
if ('serviceWorker' in navigator) {
  // If a page is already controlled by an old SW, reload once when a new SW
  // takes over so a fresh shell + latest episode list replace the cached ones.
  // (Guarded on hadController so a brand-new visit — where clients.claim fires
  // controllerchange on first install — doesn't trigger a spurious reload.)
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) window.location.reload();
  });
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
setTab(S.tab || 'listen');
