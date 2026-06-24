'use strict';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const DATA = 'data/';
const DAY = 86400000;
const SRS_DAYS = [0, 1, 3, 7, 21]; // Leitner box -> days until due

const audio = new Audio();
audio.preload = 'metadata';
let INDEX = null, CUR = null, DECK = null;

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
  ({ listen: viewListen, vocab: viewVocab, archive: viewArchive }[tab])();
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

// ================= VOCAB (flashcards + SRS) =================
async function buildDeck() {
  if (!INDEX) INDEX = await getJSON(`${DATA}index.json`);
  const cards = [];
  for (const e of INDEX.episodes) {
    if (!e.vocabCount) continue;
    try {
      const v = await getJSON(`${DATA}episodes/${e.date}/vocab.json`);
      v.cards.forEach(c => cards.push(Object.assign({ date: e.date }, c)));
    } catch {}
  }
  DECK = cards;
}
function dueCards(filter) {
  const t = todayDay();
  return DECK.filter(c => filter === 'All' || c.lang === filter)
    .map(c => ({ c, srs: S.srs[c.id] || { box: 0, due: 0 } }))
    .filter(x => x.srs.due <= t)
    .sort((a, b) => a.srs.due - b.srs.due);
}
let vFilter = 'All', vQueue = [], vIdx = 0, vFlipped = false;

async function viewVocab() {
  const view = $('#view');
  $('#ep-sub').textContent = '';
  if (!DECK) { view.innerHTML = `<div class="empty">Loading vocab…</div>`; await buildDeck(); }
  vQueue = dueCards(vFilter); vIdx = 0; vFlipped = false;
  renderVocab();
}

function renderVocab() {
  const view = $('#view');
  const langs = ['All', 'Mandarin', 'Tagalog'];
  const head = `<div class="deckhead">
      <div class="seg-filter">${langs.map(l =>
        `<button class="${l === vFilter ? 'on' : ''}" data-l="${l}">${l}</button>`).join('')}</div>
      <span class="spacer"></span>
      <span class="pill">${DECK.length} cards total</span>
    </div>`;

  if (!vQueue.length) {
    view.innerHTML = head + `<div class="card empty">
        ✓ All caught up on ${vFilter === 'All' ? 'every' : vFilter} card for today.<br><br>
        <button class="iconbtn" id="practice">Practice anyway</button></div>`;
    wireFilters();
    const p = $('#practice'); if (p) p.onclick = () => {
      vQueue = DECK.filter(c => vFilter === 'All' || c.lang === vFilter); vIdx = 0; vFlipped = false; renderVocab();
    };
    return;
  }

  const card = vQueue[vIdx].c;
  const isZh = card.lang === 'Mandarin';
  view.innerHTML = head + `
    <div class="progress">${vIdx + 1} / ${vQueue.length} due${vFilter !== 'All' ? ' · ' + vFilter : ''}</div>
    <div class="flash ${vFlipped ? 'flipped' : ''}" id="flash">
      <div class="inner">
        <div class="face front">
          <span class="lang-tag pill">${card.lang}</span>
          <div class="word">${card.word}</div>
          <div class="roman">${card.pinyin || card.pronunciation || ''}</div>
          ${card.tones ? `<div class="tones">tones: ${card.tones}</div>` : `<div class="tones">${card.pronunciation || ''}</div>`}
          <div class="tap-hint">tap to flip
            <button class="speak" id="speak">🔊 say it</button></div>
        </div>
        <div class="face back">
          <span class="lang-tag pill">${card.lang}${card.tiesTo ? ' · ' + card.tiesTo : ''}</span>
          <div class="meaning">${card.meaning}</div>
          <div class="ex">
            <div class="o">${card.example || ''}</div>
            ${card.examplePinyin ? `<div class="p">${card.examplePinyin}</div>` : ''}
            ${card.exampleMeaning ? `<div class="m">${card.exampleMeaning}</div>` : ''}
          </div>
          ${card.note ? `<div class="note">${card.note}</div>` : ''}
          <div class="tap-hint">tap to flip back</div>
        </div>
      </div>
    </div>
    <div class="deck-actions">
      <button class="btn-review" id="again">Review again</button>
      <button class="btn-know" id="know">Got it</button>
    </div>`;

  wireFilters();
  $('#flash').onclick = e => { if (e.target.id === 'speak') return; vFlipped = !vFlipped; $('#flash').classList.toggle('flipped'); };
  const sp = $('#speak'); if (sp) sp.onclick = e => { e.stopPropagation(); speak(card); };
  $('#again').onclick = () => grade(card, false);
  $('#know').onclick = () => grade(card, true);
}

function wireFilters() {
  $$('.seg-filter button').forEach(b => b.onclick = () => {
    vFilter = b.dataset.l; vQueue = dueCards(vFilter); vIdx = 0; vFlipped = false; renderVocab();
  });
}

function grade(card, known) {
  const t = todayDay();
  const cur = S.srs[card.id] || { box: 0, due: 0 };
  const box = known ? Math.min(cur.box + 1, SRS_DAYS.length - 1) : 0;
  S.srs[card.id] = { box, due: t + SRS_DAYS[box] };
  saveState();
  toast(known ? `Nice — back in ${SRS_DAYS[box]||0 ? SRS_DAYS[box] + 'd' : 'soon'}` : 'Queued to review');
  vIdx++; vFlipped = false;
  if (vIdx >= vQueue.length) viewVocab(); else renderVocab();
}

function speak(card) {
  if (!('speechSynthesis' in window)) { toast('Speech not supported'); return; }
  const u = new SpeechSynthesisUtterance(card.word);
  u.lang = card.lang === 'Mandarin' ? 'zh-CN' : 'fil-PH';
  u.rate = card.lang === 'Mandarin' ? 0.75 : 0.9;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
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
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
setTab(S.tab || 'listen');
