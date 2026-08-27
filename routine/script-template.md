# The Morning Commute — Two-Host Script (LONG / 1.5x edition)
### <Weekday>, <Month> <D>, <YYYY>

**Voices:** ALEX = Host A, domain expert (Sulafat). SAM = Host B, sharp generalist (Charon).
**Style (render):** Two polished financial-news anchors — crisp, authoritative, controlled energy, British accent.
**Audience assumption:** fluent in markets and current events. No 101 explainers; lead with the number and the second-order read.
**Segment rules:** open straight into the first story — NO run-of-show / segment preview in the cold open. There is NO meme segment. Close on a ~1 min "One Good Thing" + a warm sign-off.

> RENDER NOTE: Only `ALEX:` / `SAM:` lines are spoken. `##` headers and `<!-- … -->` comments are silent. ONE line per turn — no markdown, no line breaks inside a turn. Numbers as NUMERALS.

<!--
HOW TO USE THIS TEMPLATE (slot-filling to save tokens & mistakes):
- Fill each segment's turns; keep the header lines and structure verbatim.
- Delete these <!-- --> guidance comments as you go (they're ignored by the parser
  and never spoken, so leaving them is harmless — but a clean script is nicer).
- Target ~28,000–31,000 chars of ALEX:/SAM: dialogue (~26–29 min). Run
  tools/check_script.py before rendering.

BREADTH > OVER-EXPLANATION (the governing rule this show is tuned for):
- EVERY turn must add a NEW fact, number, or genuinely new angle. CUT any turn
  whose only job is to restate the prior turn or perform curiosity ("What's the
  read on it?", "Is that actually X though?", "That's a strange combination").
- Per-section FOLLOW-UP CAP: the LEAD story of a section gets at most ONE
  follow-up exchange; secondary stories get ZERO. Spend the reclaimed room on
  MORE of the day's important news (an extra world headline, a second arts item),
  not more back-and-forth on the same fact.
- EXEMPT from the cap — depth is the point in these two: the DEEP DIVE (one thing,
  go deep) and OP-EDS (the steelman → counter-take is a real second angle, keep it).
- The MARKET segment is the biggest trim: don't read every index aloud — the
  Markets tab shows the full levels. Name only the notable move + why, then spend
  the segment on ANALYSIS / OPINION, not a numbers readout.

IN-LANGUAGE NEWS BEATS (language that REPLACES English, doesn't add length) —
ASYMMETRIC TRANSLATION POLICY, matched to the listener's level in each language:
- TAGALOG IS NEVER TRANSLATED (heritage speaker — it stands on its own):
  PHILIPPINES delivers 2–3 of the lead politics/economy sentences in NATURAL
  TAGALOG with NO English gloss after them, then continues in English.
- MANDARIN IS ALWAYS TRANSLATED (HSK-4 learner — unglossed Mandarin is noise):
  CHINA delivers the LEAD sentence in MANDARIN (汉字) IMMEDIATELY followed by its
  English translation, using an HSK-4 connective the listener is weak on
  (尽管…还是, 一旦, 既然…就, 反而, 不仅…而且), then continues in English. EVERY
  Mandarin sentence anywhere in the show gets this same immediate translation.
  The app auto-slows any Mandarin turn to 0.5× and offers tap-to-translate.
- TAGALOG VOCAB sits right BEFORE Philippines and MANDARIN VOCAB right BEFORE
  China — teach the two words, then immediately hear them used in that news beat.
-->

---

## COLD OPEN
<!-- SAM: greet — "Good morning, this is The Morning Commute. <Weekday>, <Month> <D>. I'm Sam."
     ALEX: "And I'm Alex." — then GO: the very next turn is already telling the first story.
     NO segment preview, NO story menu, NO throughline/thesis announcement ("today's
     throughline…", "we'll trace that from…"). ~2 turns total. The throughline surfaces
     through callbacks DURING the show, never as a table of contents at the top. -->

## SEGMENT ONE — HEADLINES
<!-- 2–3 WORLD stories — CURRENT EVENTS (politics, geopolitics, conflict, elections, policy, society), NOT market moves. Lead with the newest datapoint; ADVANCE running stories, don't recap from zero. FOLLOW-UP CAP: lead story ≤1 follow-up, others 0 — use the room for a third headline when the day warrants it. -->

## SEGMENT ONE — U.S. BUSINESS
<!-- 2 US-business stories. Finance-desk framing: number first, then the "why it matters." Cap: 1 follow-up on the lead, 0 on the second. -->

## SEGMENT ONE — INTERNATIONAL BUSINESS & POLITICS
<!-- 2 international stories — lean politics/current events over markets. Cap: 1 follow-up on the lead, 0 on the second. Vary the regions across the week. -->

## SEGMENT TWO — MARKET OVERVIEW
<!-- NO TAPE CHECK — never open with a run of index closes; the MARKETS TAB shows every level. Read a number aloud ONLY for a genuinely MAJOR swing (≈ ≥1.5% on a major index, a record close, ≥10 bp one-day rates move, ≥2% commodity/FX move with a real catalyst). Sub-threshold moves: at most one clause, NO numbers ("equities drifted — it's on the Markets tab"). Spend the whole segment on ANALYSIS / OPINION — the "why," the tension, what to watch. Quiet tape = one line and move on. REAL FMP numbers only — never from memory. Also emit routine/markets-<date>.json (see the command file) so the tab is populated. -->

## SEGMENT THREE — DEEP DIVE
<!-- ~5 min on ONE thing, going DEEP (NOT subject to the follow-up cap) — this is where the time trimmed from the market recap goes. Pick EITHER a standout feature from one of the subscribed newsletters (inbox) OR a genuinely viral article/thread on X or Reddit (high engagement, being widely discussed right now). Set up the piece, then bring the hosts' real analysis: the argument, what's contested, the second-order read, why it matters to this listener. Attribute the source clearly ("a feature in <newsletter>", "a thread blowing up on <X/Reddit>"). Must be FRESH vs the ledger. -->

## SEGMENT FOUR — ENERGY / DATA CENTERS / UTILITIES
<!-- GO DEEP (SemiAnalysis / Utility Dive level): specific projects, MW/GW & capex figures, off-takers, interconnection-queue and transformer/turbine bottlenecks, the second-order read. NOT a 101. Lead with the new data point. This is the listener's professional core — density here is welcome, not over-explanation. -->

## SEGMENT FIVE — TAGALOG VOCAB
<!-- 2 TAGALOG words tied to today's Philippines stories, each NEW vs the ledger (run check_dedup). Conducted ENTIRELY IN TAGALOG — definitions, register notes, contrasts, examples, everything; NO English anywhere in this segment (heritage speaker; English is filler here). Natural spelling. Spend the time on connotation, register, and when you'd actually use it. These two words then RECUR (untranslated) in the Philippines segment that follows. -->

## SEGMENT SIX — PHILIPPINES
<!-- LEAD with politics + business/economy (national politics/governance, BSP policy + peso, major deals). Deliver 2–3 lead sentences in NATURAL TAGALOG with NO English translation after them (using today's two Tagalog vocab words where they fit), then continue in English for the rest of the beat. Weather ONLY if there's an active PAGASA storm/landfall/major flooding. NO PSEi unless it made a major move. Tie back to the throughline. Follow-up cap applies to the English news turns. -->

## SEGMENT SEVEN — MANDARIN VOCAB
<!-- 2 MANDARIN words tied to today's China story, each NEW vs the ledger. EXPLANATIONS IN ENGLISH (register 书面语/口语, near-synonym contrast, collocation pattern); EXAMPLE SENTENCES in Mandarin (汉字), each IMMEDIATELY followed by its English translation in parentheses. HSK-4; ≥1 an advanced connective / abstract collocation (NOT a concrete noun). No tone-drilling. These two words then RECUR in the China segment that follows. -->

## SEGMENT EIGHT — CHINA
<!-- 1 China item, through the two-speed / debt-deflation lens. Deliver the LEAD sentence in MANDARIN (汉字) IMMEDIATELY followed by its English translation — using an HSK-4 connective and today's two Mandarin vocab words where they fit — then continue in English. Every Mandarin sentence in this beat gets the immediate English translation. The app auto-slows Mandarin turns to 0.5×. -->

## SEGMENT NINE — ARTS & CULTURE
<!-- ~4 min. LEAD with visual & fine art (exhibitions, biennials, art fairs, auctions, gallery shows), opera & classical, and literature (releases, prizes, criticism); theater & dance welcome. Film/TV/pop is a MINOR slice. Critic's eye — the work, the maker, why it matters — not a listings roundup. 1 follow-up cap; use the room for a second art item when there's a strong one. Avoid items covered in recent episodes. -->

## SEGMENT TEN — OP-EDS & COMMENTARY
<!-- ~3 min. 1–2 notable opinion pieces/editorials shaping the debate right now (NYT/WSJ/FT/WaPo/Bloomberg Opinion/Economist/Atlantic/Foreign Affairs + popular Substack/viral op-eds). Name the writer + outlet, STEELMAN the argument, then the sharp COUNTER-take (NOT subject to the follow-up cap — the counter is a real second angle). Distinct from the Deep Dive. Fresh vs the ledger; attribute clearly. -->

## SEGMENT ELEVEN — ONE GOOD THING
<!-- One uplifting story — PREFER a personal human-interest story (someone's quiet, unprompted generosity; a family reunited; an individual overcoming adversity) over nature/wildlife/space trivia (whale counts, fossil finds, eclipses), which read as trivia rather than something to feel something about. Clean arc, zero editorializing, no caveat needed. Warm sign-off. (Do NOT include driving references unless the listener actually drives.) -->
