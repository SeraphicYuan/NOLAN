"""P0.1 — word-level narration → scene sync.

`audio.mjs sync-durations` pins only the 7 FRAME boundaries; inside a frame the scene cuts were
author-typed open-loop (audio_meta.words was empty), so visuals drift ahead of narration (measured
5–25s on v2). This closes that seam:

  1. align_voices  — run the existing whisper aligner over each assets/voice/0N.wav, write per-word
                     times into audio_meta.voices[].words (SECTION-relative). Cached by wav mtime.
  2. place_scenes  — set each scene.start/dur to the moment its ANCHOR (the distinctive SPOKEN phrase
                     it illustrates) is said. Absent an anchor, fall back to the scene's visible text.
                     Monotonic-clamped; if a frame's anchors don't resolve in order, warn + fall back
                     to proportional spacing FOR THAT FRAME ONLY (never silently).

  3. _retime_reveals — LAYER 2: pull each DATA element (chart bar, stat item, sankey ribbon, …) onto
                     the moment its narration anchor is spoken (`_cue`), so a number reveals AS the VO
                     says it. The composer's shared scheduler (compose._reveal_times) does the LAYER-1
                     spread across the window for everything unanchored; this only pins the anchored ones.
                     Numbers are canonicalized on both sides (`_collapse_nums`) so a spelled-out anchor
                     lands on Whisper's digits.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_ANCHOR_TEXT_KEYS = ("anchor", "operative")            # prefer the spoken anchor; then the operative word
_VISIBLE_TEXT_KEYS = ("lines", "title", "titleHi", "kicker", "sub", "label", "quote", "headline")

try:                                                   # per-block readable minimums (single source of truth)
    from nolan.style_contract.metrics import (MIN_READABLE as _MIN_READABLE, BLOCK_FAMILY as _BF,
                                              scene_media as _scene_media)
    _MOTION_BLOCKS = {b for b, f in _BF.items() if f == "dataviz"}   # animate continuously → not a static hold
except Exception:
    _MIN_READABLE = {"newshead": 5.0, "comparison": 5.0, "document": 5.0, "timeline": 5.0}
    _MOTION_BLOCKS = {"stat", "chart", "geo", "diagram", "timeline"}
    _scene_media = lambda block, data: (data.get("ground", {}) or {}).get("kind") or "none"


def _voice_wavs(comp_dir: Path) -> List[Path]:
    return sorted((comp_dir / "assets" / "voice").glob("[0-9]*.wav"))


def align_voices(comp_dir, force: bool = False) -> Dict:
    """Force-align each section wav → audio_meta.voices[].words (section-relative). Idempotent:
    skips a voice whose words are already present (unless force). Returns a per-voice summary."""
    from nolan.flows import source
    comp_dir = Path(comp_dir)
    meta_path = comp_dir / "audio_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    voices = meta.get("voices", [])
    by_frame = {v.get("frame"): v for v in voices}
    wavs = _voice_wavs(comp_dir)
    todo = []
    for i, wav in enumerate(wavs, start=1):
        v = by_frame.get(i)
        if v is not None and not force and (v.get("words")):
            continue
        todo.append((i, wav))
    summary = {"aligned": [], "skipped": len(wavs) - len(todo)}
    if todo:
        words_by_stem = source.word_timestamps([w for _, w in todo])   # {stem: [{word,start,end}]}
        for i, wav in todo:
            words = words_by_stem.get(wav.stem, [])
            v = by_frame.get(i)
            if v is not None:
                v["words"] = words
                summary["aligned"].append({"frame": i, "words": len(words)})
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return summary


def _scene_query(sc: dict) -> str:
    """The phrase to locate in the narration — the spoken anchor if the author gave one, else the
    scene's visible text (best-effort; typography like '61,000' won't match spoken 'sixty-one thousand')."""
    d = sc.get("data", {}) or {}
    for k in _ANCHOR_TEXT_KEYS:
        val = d.get(k) or sc.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    parts: List[str] = []
    for k in _VISIBLE_TEXT_KEYS:
        val = d.get(k)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(x) for x in val)
    return " ".join(parts).strip()


def _proportional(n: int, frame_dur: float) -> List[float]:
    return [round(frame_dur * j / n, 3) for j in range(n)]


def _norm(s: str) -> List[str]:
    try:
        from nolan.aligner import normalize_text
        return normalize_text(s).split()
    except Exception:
        import re
        return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


# --- ④ VO↔script fidelity + ⑤ anchor↔transcript suggestion (homer cold-start POST_MORTEM) ---------
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "it", "that", "this", "for", "with",
         "was", "were", "by", "as", "on", "at", "be", "are", "not", "but", "its", "his", "her", "their",
         "they", "we", "you", "have", "had", "from", "then", "so", "no", "one"}


def _content(text: str) -> List[str]:
    return [t for t in _norm(text) if t not in _STOP and len(t) > 1]


_NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                 "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
                 "hundred", "thousand", "million", "billion", "trillion", "percent", "negative", "point"}


def _numberish_anchor(text: str) -> bool:
    """The anchor LEADS with a number — digits OR spelled-out. Whisper transcribes numbers as DIGITS
    ('900 million', '$13.1 billion', '60%'), never spelled-out, so an anchor that starts on a number-word
    usually fails to match. Prefer a nearby non-numeric verbatim span. (Checks the leading tokens — a number
    deeper in the phrase is fine as long as the head is content words.)"""
    if not text:
        return False
    toks = _norm(text)[:3]
    return any(any(c.isdigit() for c in t) or t in _NUMBER_WORDS for t in toks)


def _dropped_sentences(source_text: str, spoken_tokens, min_cover: float = 0.3) -> List[Dict]:
    """SOURCE sentences whose CONTENT words are almost entirely ABSENT from the spoken transcript — i.e.
    the cloned VO DROPPED that line (vs merely garbling a word or two, which the weak-anchor check
    handles). The low floor keeps this to real drops, not hyphen/possessive mis-transcriptions. Protects
    "narration owns duration": if the VO ≠ the script, authoring against the script is wrong (homer ④)."""
    import re
    spoken = set(spoken_tokens)
    out = []
    for s in re.split(r"(?<=[.!?])\s+", (source_text or "").strip()):
        toks = _content(s)
        if len(toks) < 3:                                # too short to judge (kicker/fragment)
            continue
        cover = sum(1 for t in toks if t in spoken) / len(toks)
        if cover < min_cover:
            out.append({"sentence": s.strip()[:90], "coverage": round(cover, 2)})
    return out


def _suggest_anchor_span(anchor: str, stream_tokens: List[str]) -> Optional[str]:
    """The transcript n-gram that best matches `anchor` — the VERBATIM tokens an author should anchor to
    instead of the script phrase Whisper garbled ('Milman Parry'→'Perry', 'rosy-fingered'→'rosy fingered').
    None when the anchor already appears exactly (no help needed) or nothing is close (homer POST_MORTEM ⑤)."""
    at = _norm(anchor)
    n = len(at)
    if not n or n > len(stream_tokens):
        return None
    best = (0, None)
    for i in range(len(stream_tokens) - n + 1):
        window = stream_tokens[i:i + n]
        overlap = sum(1 for a, b in zip(at, window) if a == b)
        if overlap == n:
            return None                                  # exact match — anchor is fine
        if overlap > best[0]:
            best = (overlap, " ".join(window))
    return best[1] if best[0] >= max(1, n // 2) else None


# --- number-aware matching (subtlety #1: Whisper writes numbers as DIGITS, authors often spell them) ---
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}
_NUMTOK = set(_UNITS) | set(_TENS) | {"hundred"} | set(_SCALES)
_DROP_NUM = {"percent", "percentage", "point"}          # normalize "sixty percent" ↔ Whisper "60%"→"60"


def _is_numtok(t: str) -> bool:
    return t in _NUMTOK or (t.isdigit()) or t in _DROP_NUM


def _parse_num_run(run: List[str]) -> str:
    """Collapse a run of number tokens (digits AND/OR spelled-out, incl. digit+scale like '900 million')
    to a single canonical integer string. Whisper and a spelled-out author phrase collapse to the SAME
    value, so '900 million' == 'nine hundred million'. Best-effort; passes odd runs through joined."""
    total, current, seen = 0, 0, False
    for t in run:
        if t in _DROP_NUM:
            continue
        seen = True
        if t.isdigit():
            current += int(t)
        elif t in _UNITS:
            current += _UNITS[t]
        elif t in _TENS:
            current += _TENS[t]
        elif t == "hundred":
            current = (current or 1) * 100
        elif t in _SCALES:
            total += (current or 1) * _SCALES[t]
            current = 0
    return str(total + current) if seen else " ".join(run)


def _collapse_nums(seq):
    """Replace each maximal number run in a token sequence with its canonical integer. `seq` items are
    either bare tokens (str) or (token, anchor_time) pairs; returns the same shape with runs collapsed
    (a collapsed run carries its FIRST token's time). Non-number tokens pass through unchanged."""
    paired = seq and not isinstance(seq[0], str)
    toks = [x[0] for x in seq] if paired else list(seq)
    times = [x[1] for x in seq] if paired else [None] * len(seq)
    out, i = [], 0
    while i < len(toks):
        if _is_numtok(toks[i]):
            j = i
            while j < len(toks) and _is_numtok(toks[j]):
                j += 1
            canon = _parse_num_run(toks[i:j])
            if canon.strip():
                out.append((canon, times[i]) if paired else canon)
            i = j
        else:
            out.append((toks[i], times[i]) if paired else toks[i])
            i += 1
    return out


def _phrase_time(phrase: str, words, after: float = 0.0) -> Optional[float]:
    """First spoken time of `phrase` (a token subsequence) at/after `after` seconds; None if unsaid.

    Uses the FLATTENED token stream (aligner.flatten_words) so a hyphenated/possessive spoken word
    contributes all its sub-tokens — the old form kept only the FIRST sub-token of each word
    (`_norm(w.word)[0]`), so 'forty-one'->'forty' and any anchor/operative containing such a word
    silently missed (holbein POST_MORTEM #5). Numbers are canonicalized on BOTH sides (subtlety #1)
    so a spelled-out anchor ('nine hundred million') lands on Whisper's digits ('900 million')."""
    from nolan.aligner import flatten_words
    toks = [t for t in _collapse_nums(_norm(phrase)) if t]
    if not toks:
        return None
    stream = _collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])   # [(canon_token, start)]
    n = len(toks)
    for i in range(len(stream) - n + 1):
        if stream[i][1] < after:
            continue
        if all(stream[i + j][0] == toks[j] for j in range(n)):
            return stream[i][1]
    return None


_ELEMENT_ANCHOR_KEYS = ("at", "anchor")     # per-element spoken-phrase anchor ("show it AS you say it")


def _retime_reveals(sc: Dict, d: Dict, words) -> int:
    """LAYER 2 — resolve each data element's narration anchor to an ABSOLUTE spoken time (`_cue`).

    The composer's shared reveal scheduler (compose._reveal_times) already SPREADS every data block's
    reveals across its window (Layer 1) and reads each element's `_cue` first — so this no longer spreads
    (that would double-schedule); it ONLY pulls anchored elements onto their spoken phrase. An element
    that carries `at` (or `anchor`) with a resolvable phrase gets `_cue` = the absolute time it's said;
    unanchored elements are left None so the composer spreads them. Field-name-agnostic: it finds ANY
    authored list-of-dicts whose elements carry an anchor, so it covers every data block (chart series,
    stat items, sankey targets, pie/funnel/cycle/…) and any future one without a per-block table.

    Idempotent: pops a stale `_cue` before re-resolving, so removing an anchor un-pins the element.
    Returns how many elements it pinned to narration time."""
    if not words:
        return 0
    start, dur = float(sc.get("start", 0) or 0), float(sc.get("dur", 0) or 0)
    done = 0
    for val in (d or {}).values():
        if not isinstance(val, list) or not any(isinstance(x, dict) for x in val):
            continue                                            # only lists-of-dicts can be element lists
        for el in val:
            if not isinstance(el, dict):
                continue
            el.pop("_cue", None)                                # clear a prior sync's placement (un-pin removed anchors)
            phrase = next((el.get(k) for k in _ELEMENT_ANCHOR_KEYS if el.get(k)), None)
            if not phrase:
                continue
            t = _phrase_time(str(phrase), words, after=start)
            if t is not None and start <= t < start + dur:
                el["_cue"] = round(t, 3)                         # ABSOLUTE; composer clamps monotonically
                done += 1
    return done


def _retime_lines(sc: Dict, d: Dict, words) -> int:
    """LAYER 2 for TEXT — resolve each on-screen LINE's spoken time → data._line_cues (absolute), so a text
    block reveals its lines AS the VO reads them (kinetic typography), not on a fixed stagger that front-loads
    the whole block seconds before the narration reaches it. For any block with `data.lines` (statement,
    juxtaposition sides, …) whose lines are (usually verbatim) script text. Monotonic; a line that doesn't
    resolve is left None so the composer spreads it. Idempotent (recomputed each sync)."""
    lines = d.get("lines")
    if not isinstance(lines, list) or not lines or not words:
        return 0
    start, dur = float(sc.get("start", 0) or 0), float(sc.get("dur", 0) or 0)
    cues, prev, done = [], start, 0
    for line in lines:
        t = None
        if isinstance(line, str) and line.strip():
            t = _phrase_time(line, words, after=prev)             # the whole line, verbatim
            if t is None:                                         # …else its first few content words
                head = " ".join(w for w in _norm(line) if w not in _STOP and len(w) > 2)
                t = _phrase_time(head, words, after=prev) if head else None
        if t is not None and start <= t < start + dur:
            cues.append(round(t, 3)); prev = t; done += 1
        else:
            cues.append(None)
    d["_line_cues"] = cues
    return done


def _cb_is_tree(nodes, links) -> bool:
    """A connection_board whose links form a FOREST when UNDIRECTED (a tree / chain / convergence — no
    undirected cycle) — NOT the shape connection_board is for. A genuine relationship WEB has at least one
    undirected cycle: a mutual/back-reference (a↔b) or two paths meeting (a→b, a→c, b→c). The OLD test keyed
    on directed IN-degree ('two parents ⇒ a web'), which mis-passed a DAG where two chains converge on one
    sink (Google→shell→land, Meta→shell→land: land has in-degree 2 but the graph is undirected-acyclic — a
    FLOW, not a web) — the 'Ownership hides' exhibit. Union-find: an edge joining two already-connected nodes
    closes an undirected cycle ⇒ web (False); no cycle ⇒ forest/flow ⇒ True (connection_board is wrong)."""
    edges = [(lk.get("from"), lk.get("to")) for lk in (links or [])
             if lk.get("from") is not None and lk.get("to") is not None]
    if not edges:
        return False
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:                          # path-compress
            parent[x], x = root, parent[x]
        return root

    for a, b in edges:
        if a == b:
            return False                                  # a self-loop is a (degenerate) cycle ⇒ don't reclassify
        ra, rb = find(a), find(b)
        if ra == rb:
            return False                                  # this edge closes an undirected cycle ⇒ a genuine web
        parent[ra] = rb
    return True                                           # no undirected cycle ⇒ tree/chain/convergence ⇒ not a web


def _spans_overlap(spans) -> bool:
    """True iff at least two duration bars overlap on the axis — the property `spans` exists to show.
    None overlapping ⇒ it's a sequence (timeline), not spans."""
    ivals = []
    for s in spans or []:
        try:
            a, b = float(s.get("start")), float(s.get("end"))
            ivals.append((min(a, b), max(a, b)))
        except (TypeError, ValueError):
            return True                                  # can't parse ⇒ don't second-guess the author
    ivals.sort()
    for i in range(1, len(ivals)):
        if ivals[i][0] < ivals[i - 1][1] - 1e-9:         # starts before the previous one ended
            return True
    return False


_DATAVIZ = {"chart", "stat", "sankey", "pie", "funnel", "quadrant", "cycle", "spectrum", "scale",
            "spans", "venn", "connection_board", "bullet_list", "ledger"}


def _data_element_count(d: Dict) -> int:
    """The reveal-element count of a data block = the length of its largest authored list-of-dicts
    (field-name-agnostic: chart series, stat items, sankey targets, pie segments, …)."""
    best = 0
    for v in (d or {}).values():
        if isinstance(v, list) and any(isinstance(x, dict) for x in v):
            best = max(best, len(v))
    return best


def _has_element_anchor(d: Dict) -> bool:
    for v in (d or {}).values():
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and (x.get("at") or x.get("anchor")):
                    return True
    return False


def _selection_mismatch(sc: Dict) -> Optional[str]:
    """The PROVABLE block-choice mismatches — a block whose data structurally CANNOT be what the block is
    FOR (an 'empty comparison': a pie with one slice, a spans with no overlap, a connection_board that is a
    flow not a web). These are deterministic and gate-worthy — `author.py`'s validate_spec REJECTS them at
    authoring (override per-scene with `data.block_ok: true` + a reason). Kept DISTINCT from the SOFT
    advisories in `_selection_advice` (a sparse block on a long hold), which are pacing judgement calls, not
    wrong-block facts. Single source of truth — the sync report, the authoring advisory, and the gate all
    read these same rules. Returns the mismatch reason (with the block to use instead) or None."""
    t, d = sc.get("type"), (sc.get("data", {}) or {})
    if t == "connection_board" and _cb_is_tree(d.get("nodes") or [], d.get("links") or []):
        return ("its links form a TREE/CHAIN/CONVERGENCE (no undirected cycle) — connection_board is for a "
                "mutual WEB. Use `diagram` (flow / hierarchy) or `timeline`.")
    if t == "spans" and len(d.get("spans") or []) >= 2 and not _spans_overlap(d.get("spans")):
        return ("none of the duration bars OVERLAP — `spans` shows COEXISTING periods; a dated sequence is a "
                "`timeline`.")
    if t == "chart" and len(d.get("series") or []) == 1:
        return "a chart of ONE value is a `stat`; charts want 3+ comparable bars/points."
    if t == "pie" and len(d.get("segments") or []) < 2:
        return "a pie needs ≥2 slices to show parts-of-a-whole; one share is a `stat`."
    if t == "venn" and len(d.get("sets") or []) < 2:
        return "a venn needs ≥2 sets to show an overlap; use `stat`/`statement`."
    return None


def _selection_advice(sc: Dict) -> Optional[str]:
    """ADVISORY (never a gate): a STRUCTURAL sign the beat picked the wrong block, OR a sparse data block
    stranded on a long hold. Editorial judgement stays with the author; this only catches shapes that are
    provably a mismatch or a guaranteed-stale hold (the acid-test 'poor block choice / reads static' class).
    Returns a short suggestion or None. Superset of `_selection_mismatch` (the gate-worthy subset) + the
    soft sparse-hold pacing advisory."""
    mm = _selection_mismatch(sc)                             # the provable, gate-worthy mismatches first
    if mm:
        return mm
    t, d = sc.get("type"), (sc.get("data", {}) or {})
    # sparse-but-long: even a perfectly spread reveal can't fill a long window with few elements. The
    # composer caps spread so an un-anchored element never waits absurdly long, so a 2-item block on a 20s
    # hold reveals in ~3s then reads STATIC. This is editorial, not motion (the acid-test's real lesson):
    dur = float(sc.get("dur", 0) or 0)
    n = _data_element_count(d)
    grounded = ((d.get("ground") or {}).get("kind") if isinstance(d.get("ground"), dict) else None) not in (None, "color", "flat")
    if t in _DATAVIZ and 0 < n <= 3 and dur >= 9.0 and not grounded and not _has_element_anchor(d):
        return (f"{n} element(s) on a {dur:.0f}s hold reads STATIC (reveals finish in ~3s, then dead air). "
                f"Anchor elements to narration with `at`, add a `data.ground` (image+kenburns / paper), or split the beat.")
    return None


def _content_time(sc, stream, freq, after, min_words=1):
    """Earliest spoken time (after `after`) where the scene's TOPIC first surfaces in the VO — the first
    spoken DISTINCTIVE content word from the scene's own labels (a word occurring just ONCE in the frame, so
    a common word can't drag the scene early). More robust than a hand-picked `anchor` that may point at a
    CLOSING detail (the 'santa cruz' bug — a water scene anchored to its final aside placed 18s late,
    overrunning the whole segment). `min_words`: require this many DISTINCT content words clustering near the
    earliest hit before trusting it — 1 for placement (floor + anchor-min already protect it), 2 for the LINT
    (an editorial kicker like 'SO WHERE I LAND' has one polysemous word that would false-flag). None if
    nothing (sufficiently corroborated) resolves. len ≥ 5 drops 4-letter homonyms ('land')."""
    d = sc.get("data", {}) or {}
    parts = []
    for k in ("kicker", "title", "titleHi", "center", "headline"):
        if isinstance(d.get(k), str):
            parts.append(d[k])
    for it in (d.get("items") or [])[:5]:                    # element labels carry the topic too
        if isinstance(it, dict) and isinstance(it.get("label"), str):
            parts.append(it["label"])
    toks = {tt for tt in _collapse_nums(_norm(" ".join(parts)))
            if len(tt) >= 5 and tt not in _STOP and freq.get(tt, 0) == 1}
    hits = sorted((s, tok) for (tok, s) in stream if tok in toks and s >= after)
    if not hits:
        return None
    if min_words <= 1:
        return hits[0][0]
    t0 = hits[0][0]
    near = {tok for (s, tok) in hits if s <= t0 + 5.0}       # distinct words within 5s of the earliest
    return t0 if len(near) >= min_words else None


# --- the ROBUST topic-opening matcher (fuzzy content WINDOW, bag-of-words) ---------------------------
# `_content_time` needs a word that is BOTH distinctive (freq==1) AND long (len≥5); an editorial kicker
# ("THE WHOLE THING") can supply distinctive words that echo a LATER VO phrase, dragging the scene late,
# while its actual opening (common, short, or stopword-separated words) is invisible. `_phrase_time`
# needs a CONTIGUOUS subsequence, which a rhetorical prefix ("Do they hand the bill…") or a dropped
# stopword ("hand bill" ≠ spoken "hand the bill") breaks. The 7:31 text-lag hit all three at once. The
# window matcher below is tolerant of all of them: it finds the narration WINDOW that best covers the
# scene's VISIBLE-text bag and returns where that coverage OPENS.
_BAG_TEXT_KEYS = ("kicker", "title", "titleHi", "headline", "center", "sub", "quote", "eyebrow", "label")

# len≥4 keeps short CONTENT words ('hand', 'bill', 'vote') but also lets common FUNCTION words through
# ('what', 'your', 'really') — and a function word said once in a frame gets full inverse-freq weight, so a
# generic pair like {what, your} spanning two unrelated sentences can falsely corroborate a scene's placement
# (the openai-debate 'belief is the business' scene matched {your@34, what@38} 52s before its real opening).
# These carry no topic, so they are dropped from the bag. Keep it to CLEAR function/filler words — a real
# content word wrongly listed here would silence a legitimate match.
_BAG_STOP = _STOP | {
    "what", "your", "really", "which", "when", "where", "would", "could", "should", "into", "about", "very",
    "just", "some", "more", "even", "only", "than", "that", "this", "they", "them", "their", "there", "here",
    "been", "being", "does", "will", "with", "from", "over", "under", "again", "once", "most", "much", "many",
    "such", "both", "each", "other", "another", "these", "those", "then", "thus", "still", "also", "well",
    "back", "down", "because", "while", "were", "have", "has", "had", "want", "need", "know", "like", "make",
    "made", "going", "gonna", "thing", "things", "stuff", "kind", "sort", "actually", "maybe", "yourself",
    "itself", "themselves", "something", "anything", "everything", "someone", "anyone", "everyone",
}


def _scene_bag(sc) -> set:
    """The set of the scene's VISIBLE-text content tokens (number-collapsed, non-stop, len≥4) — every word
    the viewer reads on screen: the title/kicker/lines PLUS each element's label/sub (chart series, spans,
    nodes, pie segments, list items). This is what should be on screen WHEN the VO says it, so it is the
    right signal to locate the scene's topic in the narration. len≥4 keeps 'hand'/'bill'/'vote' while
    dropping noise; proper nouns ('Disney','OpenAI') are strong, discriminative hits."""
    d = sc.get("data", {}) or {}
    parts: List[str] = []

    def add(v):
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    parts.append(x)
                elif isinstance(x, dict):
                    for kk in ("label", "sub", "text", "name"):
                        if isinstance(x.get(kk), str):
                            parts.append(x[kk])

    for k in _BAG_TEXT_KEYS:
        add(d.get(k))
    add(d.get("lines"))
    for k in ("items", "nodes", "spans", "series", "segments", "sides", "steps", "rows", "points"):
        add(d.get(k))
    return {tt for tt in _collapse_nums(_norm(" ".join(parts))) if len(tt) >= 4 and tt not in _BAG_STOP}


def _shared_bag_tokens(scenes) -> set:
    """Tokens that appear in the visible-text bag of ≥2 scenes IN THE SAME FRAME — the vocabulary the scenes
    SHARE (adjacent beats about the same entities: a shell-ownership web and a 'same move 60 years apart'
    timeline both name Google/Meta/Jetstream). A shared word does NOT distinguish which scene the VO is on,
    so it must not corroborate a scene's placement (else a 'Disney, 60 years ago' beat gets pulled 14s early
    onto its neighbour's 'Google/Meta shells' narration). `_content_window_time` down-weights these."""
    from collections import Counter
    c = Counter()
    for sc in scenes:
        c.update(_scene_bag(sc))
    return {tok for tok, n in c.items() if n >= 2}


def _content_window_time(sc, stream, freq, after, window=6.0, min_weight=1.5, shared=None):
    """ROBUST topic-opening time via a fuzzy content-WINDOW. Scans narration in time order and returns the
    time of the EARLIEST `window`-second span that CORROBORATES the scene's visible-text bag (`_scene_bag`) —
    i.e. where the scene's topic first SURFACES in the VO.

    Robust where exact/distinctive matching is blind: paraphrase, rhetorical prefixes, stopword-separated
    phrases, and editorial kickers that echo a later phrase (the 7:31 lag). Earliest-corroborated (NOT
    globally-densest) is deliberate: a scene's on-screen text is often a NOMINALIZED paraphrase of the VO
    ('preference'/'prediction' for spoken 'prefer'/'likely'), so its bag can match a LATER coincidental
    cluster of generic words more densely than its own opening — taking the densest span mislocated a
    'steelman both sides' beat onto a later 'the honest version' sentence (a false mis-order). The opening
    is what we want anyway: place the scene WHEN its topic first comes up. Corroboration-gated so a lone
    common word — a generic pair like {never, people} spanning two sentences — can't place a scene: the span
    must carry ≥2 DISTINCT bag words whose combined inverse-frequency weight (Σ 1/freq — said once ≈1.0, said
    5× ≈0.2) ≥ `min_weight` (default 1.5, so it needs ONE distinctive word + a second, or three common words;
    two common words score 1.0 and are rejected). Words in `shared` (vocabulary this scene shares with a
    sibling — see `_shared_bag_tokens`) are down-weighted ×0.25 so a scene can't be placed on its neighbour's
    entities. None when nothing corroborated resolves (caller falls back to anchor/distinctive/aligner signals)."""
    bag = _scene_bag(sc)
    if not bag:
        return None
    sh = shared or frozenset()
    hits = sorted((s, tok) for (tok, s) in stream if tok in bag and s >= after)
    if len(hits) < 2:
        return None
    for i, (t0, _tok) in enumerate(hits):
        seen = {}
        for (t, tok) in hits[i:]:
            if t > t0 + window:
                break
            w = (1.0 / max(1, freq.get(tok, 1))) * (0.25 if tok in sh else 1.0)
            seen.setdefault(tok, w)
        if len(seen) >= 2 and sum(seen.values()) >= min_weight:
            return round(t0, 3)                              # earliest span that corroborates → topic opening
    return None


def _topic_open_time(sc, stream, freq, after=0.0, shared=None):
    """The single most-robust estimate of when a scene's topic OPENS in the VO: the earliest of the fuzzy
    content-window (`_content_window_time`, sibling-discriminated) and the distinctive-word time
    (`_content_time`, corroborated). Used by BOTH placement and the lag lint so they never disagree
    (placement can't fix a lag the lint still reports, or vice-versa). None if neither resolves."""
    cw = _content_window_time(sc, stream, freq, after, shared=shared)
    cd = _content_time(sc, stream, freq, after, min_words=2)
    cands = [x for x in (cw, cd) if x is not None]
    return min(cands) if cands else None


def _resolve_scene_starts(scenes, words, frame_dur, aligner_raw):
    """Scene start times — INDEPENDENT per-scene anchoring + OUTLIER ISOLATION so a mis-sync can't cascade.

    1. OWN time — each scene's start is where its TOPIC first surfaces in the narration: the EARLIER of its
       explicit `anchor` (number-aware) and its distinctive content (`_content_time`), computed INDEPENDENTLY
       (NOT chained off the previous scene's placement). This auto-corrects an anchor pointing at a late /
       closing phrase, and — crucially — a bad anchor on scene N no longer pushes N+1's search past N+1's own
       content. The aligner's fuzzy time is the fallback when neither exact signal fires.
    2. TRUST the consensus — the scenes whose own-times form the LONGEST strictly-increasing run (in scene
       order) are trusted and PINNED to their own time. A scene whose own-time breaks that order is an OUTLIER
       (a bad anchor or a mis-ordered scene): it is ISOLATED and INTERPOLATED between its trusted neighbours,
       so its error stays WITHIN ITS OWN WINDOW and never accumulates onto the rest of the frame.
    Always monotonic. Returns (starts, resolved_scene_ids). (A genuinely mis-ORDERED scene is isolated here so
    it doesn't drag its neighbours, and separately flagged by `_visual_lag_flags` for a spec reorder.)"""
    n = len(scenes)
    if n == 0:
        return [], set()
    from nolan.aligner import flatten_words
    stream = _collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)]) if words else []
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    lo, hi = 0.3, frame_dur - 0.3                            # a global window (NOT prev-dependent → no cascade)
    shared = _shared_bag_tokens(scenes)                      # vocabulary siblings share → can't corroborate placement
    own = [None] * n
    own[0] = 0.0                                             # scene 1 opens the frame
    for j in range(1, n):
        q = _scene_query(scenes[j])
        anc_t = _phrase_time(q, words, after=lo) if (q and words) else None
        con_t = _content_time(scenes[j], stream, freq, lo) if stream else None
        # ROBUST candidate: the fuzzy content-window topic-opening — beats an exact-but-LATE anchor when the
        # topic opens earlier than the anchored (often closing) clause (the 7:31 santa-cruz-of-text bug). A
        # spuriously-early window that breaks scene order is caught by the LIS outlier isolation below.
        win_t = _content_window_time(scenes[j], stream, freq, lo, shared=shared) if stream else None
        cands = [x for x in (anc_t, con_t, win_t) if x is not None and lo <= x < hi]
        if cands:
            own[j] = round(min(cands), 3)
        else:
            a = aligner_raw[j] if (aligner_raw and j < len(aligner_raw)) else None
            own[j] = round(float(a), 3) if (a is not None and lo < float(a) < hi) else None
    # trust = the longest strictly-increasing (by ≥0.35s) run of own-times, in scene order (an O(n²) LIS);
    # outliers (own-time out of order) are dropped → interpolated, isolating their error to their own window.
    idx = [j for j in range(n) if own[j] is not None]
    dp = [1] * len(idx)
    par = [-1] * len(idx)
    for k in range(len(idx)):
        for l in range(k):
            if own[idx[l]] + 0.35 <= own[idx[k]] and dp[l] + 1 > dp[k]:
                dp[k], par[k] = dp[l] + 1, l
    trusted = {0}
    if idx:
        best = max(range(len(idx)), key=lambda k: dp[k])
        while best != -1:
            trusted.add(idx[best])
            best = par[best]
    resolved = {scenes[j].get("id", f"s{j}") for j in trusted if own[j] is not None} | {scenes[0].get("id", "s0")}
    # pin trusted scenes to their own time; interpolate the rest between trusted anchors (+ a virtual end)
    t = [own[j] if j in trusted else None for j in range(n)]
    t[0] = 0.0
    pts = [(j, t[j]) for j in range(n) if t[j] is not None] + [(n, float(frame_dur))]
    out = [0.0] * n
    for k in range(len(pts) - 1):
        (j0, t0), (j1, t1) = pts[k], pts[k + 1]
        out[j0] = t0
        span = j1 - j0
        for m in range(1, span):
            if j0 + m < n:
                out[j0 + m] = round(t0 + (t1 - t0) * m / span, 3)
    for j in range(1, n):                                    # guard against tiny equalities → strictly increasing
        if out[j] <= out[j - 1]:
            out[j] = round(out[j - 1] + 0.05, 3)
    return out, resolved


def _relieve_short_windows(scenes, frame_dur, max_passes=6):
    """#1 — no scene renders below its READABLE minimum. After placement, a scene squeezed under
    MIN_READABLE (a 0.5s flash the eye can't read — the perceptual gate's 'illegible / layout empty' class)
    BORROWS time from a neighbour that has slack (its dur above ITS own floor), never pushing that neighbour
    below its minimum. Greedy boundary relaxation, order-preserving + monotonic (slack-capped moves can't
    cross boundaries). A resolved scene may drift slightly off its spoken word, but a legible-slightly-early
    beat beats an unreadable flash. If the frame is genuinely over-packed (no neighbour has slack), it does
    its best and the residual stays flagged. Mutates sc.start/dur in place; returns {fixed, residual}."""
    n = len(scenes)
    if n < 2 or frame_dur <= 0:
        return {"fixed": 0, "residual": []}
    mn = [max(0.6, _MIN_READABLE.get(sc.get("type"), 3.0)) for sc in scenes]
    b = [float(sc.get("start", 0) or 0) for sc in scenes] + [float(frame_dur)]   # boundaries b[0..n]
    before = [round(b[j + 1] - b[j], 3) for j in range(n)]

    def dur(j):
        return b[j + 1] - b[j]

    for _ in range(max_passes):
        moved = False
        for j in range(n):
            need = mn[j] - dur(j)
            if need <= 1e-3:
                continue
            if j + 1 < n:                                     # borrow from the NEXT scene's slack (b[j+1] → right)
                take = min(need, max(0.0, dur(j + 1) - mn[j + 1]))
                if take > 1e-3:
                    b[j + 1] += take; need -= take; moved = True
            if need > 1e-3 and j > 0:                         # borrow the rest from the PREV scene (b[j] → left)
                take = min(need, max(0.0, dur(j - 1) - mn[j - 1]))
                if take > 1e-3:
                    b[j] -= take; moved = True
        if not moved:
            break

    fixed, residual = 0, []
    for j in range(n):
        nd = round(max(0.1, b[j + 1] - b[j]), 3)
        if before[j] + 1e-3 < mn[j] <= nd + 1e-3:
            fixed += 1
        if nd + 1e-3 < mn[j]:
            residual.append({"scene": scenes[j].get("id"), "block": scenes[j].get("type"),
                             "dur": nd, "min": round(mn[j], 1)})
        scenes[j]["start"] = round(max(0.0, b[j]), 3)
        scenes[j]["dur"] = nd
    return {"fixed": fixed, "residual": residual}


def _visual_lag_flags(scenes, words, min_lag=6.0):
    """Report where a scene's VISUAL lags the VO — the drift the eye catches (the 3:13-says-43%-but-shows-
    at-3:33 bug; the 7:31 text-block-appears-late bug). Two kinds, keyed on each scene's ROBUST topic-open
    time (`_topic_open_time` = earliest of the fuzzy content-window and the distinctive-word time — the SAME
    signal placement uses, so the lint can't flag a lag placement already fixed, nor miss one placement can't):
      - LAG: the scene is placed well AFTER its topic first surfaces (a late/closing anchor left the PREVIOUS
        scene overrunning; or the topic opens on paraphrased/common words the old distinctive-word check missed).
      - MIS-ORDER: the scene's topic is narrated ENTIRELY before its predecessor's — the scenes are in the
        wrong order for the narration; placement can't fix this without reordering the spec.
    Each lag flag carries `hard` = the lag is bad enough to BLOCK the render (see `_hard_lag_flags`)."""
    if not words:
        return []
    from nolan.aligner import flatten_words
    stream = _collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    shared = _shared_bag_tokens(scenes)
    flags, prev_ct = [], None
    for sc in scenes:
        ct = _topic_open_time(sc, stream, freq, 0.0, shared=shared)   # robust: fuzzy window ∪ distinctive word (earliest)
        start = float(sc.get("start", 0) or 0)
        # `authored_here`: the scene carries an explicit anchor that resolves AT ~its placement — the author
        # DELIBERATELY pinned it late (the late-anchor ◆ advisory covers it). Such a lag is a judgement call,
        # not a placement failure, so it stays SOFT; only drift NOT justified by the author's own anchor (a
        # scene LIS-stranded away from where its anchor / content say, or an unanchored over-reach) is HARD.
        anc = (sc.get("data", {}) or {}).get("anchor") or sc.get("anchor") or (sc.get("data", {}) or {}).get("operative")
        anc_t = _phrase_time(str(anc), words, after=0.3) if isinstance(anc, str) and anc.strip() else None
        authored_here = anc_t is not None and abs(anc_t - start) <= _ANCHOR_INTENT_TOL
        if ct is not None:
            if start - ct > min_lag:
                flags.append({"scene": sc.get("id"), "block": sc.get("type"), "kind": "lag",
                              "start": round(start, 1), "content_at": round(ct, 1), "lag": round(start - ct, 1),
                              "hard": (start - ct) >= _HARD_LAG_S and not authored_here})
            if prev_ct is not None and ct < prev_ct - 3.0:
                flags.append({"scene": sc.get("id"), "block": sc.get("type"), "kind": "misorder",
                              "content_at": round(ct, 1), "prev_content_at": round(prev_ct, 1),
                              "hard": not authored_here})
            prev_ct = ct
    return flags


# A scene whose visual trails its narration by ≥ this is a defect the eye plainly catches — the finish DAG
# hard-blocks it (escape: HF_ALLOW_LAG=1). Placement (window matcher + LIS) fixes what it can first, so this
# only fires on a lag placement COULDN'T resolve (an interpolated outlier still late) or a genuine mis-order.
_HARD_LAG_S = 6.0
# how near an explicit anchor must resolve to a scene's placement to count as "the author put it here on
# purpose" (→ soft advisory, not a hard block). Wider than a couple of words so a late-clause anchor still reads
# as intentional; a scene stranded WELL past its anchor is a genuine placement failure and stays hard.
_ANCHOR_INTENT_TOL = 4.0


def _late_anchor_flags(scenes, words):
    """ANCHOR-QUALITY (the authoring root fix, #B): a scene whose explicit `anchor` resolves well AFTER its
    topic opens — a CLOSING/late phrase (the 'santa cruz' anchor on a water scene). Content-time placement
    now auto-corrects it, but a late anchor is FRAGILE (it fails the moment the scene lacks matching content,
    and it makes the scene an interpolated outlier). Nudge the author to anchor the OPENING. Reports the
    anchor time, the content time, and the earlier phrase to use. Requires both to resolve."""
    if not words:
        return []
    from nolan.aligner import flatten_words
    stream = _collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    shared = _shared_bag_tokens(scenes)
    out = []
    for sc in scenes:
        anc = (sc.get("data", {}) or {}).get("anchor") or sc.get("anchor") or (sc.get("data", {}) or {}).get("operative")
        if not isinstance(anc, str) or not anc.strip():
            continue
        at = _phrase_time(anc, words, after=0.3)
        ct = _topic_open_time(sc, stream, freq, 0.3, shared=shared)   # robust topic-open (window ∪ distinctive word)
        if at is not None and ct is not None and at - ct > 6.0:
            out.append({"scene": sc.get("id"), "block": sc.get("type"), "anchor": anc[:40],
                        "anchor_at": round(at, 1), "content_at": round(ct, 1)})
    return out


def _number_provenance_flags(scenes, words, min_values=3):
    """#3 / A-P1 — a data-viz block whose displayed NUMBERS trace to NOTHING is a fabrication risk: the
    'benefits spread / costs don't' sankey invented a $100 → 34/24/18/14/10 breakdown the script never gave
    (the block DEMANDED weights; the author made them up). A number is LEGITIMATE if it traces to any of:
    (a) spoken in the narration (number-aware — a charted 800 matches spoken '800 billion'), (b) an explicit
    `value_source` (element-level or scene-level `data.value_source`), or (c) a dataset cell (A-P2). A scene
    that shows `min_values`+ numbers with NONE traceable is flagged (the hard gate in the finish DAG rejects
    it). Element/scene-level `value_source` exempts those numbers."""
    if not words:
        return []
    from nolan.aligner import flatten_words
    spoken = set()
    for (t, _s, _e) in flatten_words(words):
        digits = "".join(c for c in t if c.isdigit())
        if digits:
            spoken.add(str(int(digits)))
    out = []
    for sc in scenes:
        if sc.get("type") not in _DATAVIZ:
            continue
        d = sc.get("data", {}) or {}
        if d.get("value_source"):                          # (b) scene-level source — every number is sourced
            continue
        vals = []
        for v in d.values():
            if isinstance(v, list):
                for el in v:
                    if isinstance(el, dict) and not el.get("value_source"):   # (b) element-level source exempts it
                        for k in ("value", "to"):
                            x = el.get(k)
                            if isinstance(x, (int, float)) and not isinstance(x, bool):
                                vals.append(x)
        if len(vals) < min_values:
            continue
        if not any(str(int(round(v))) in spoken for v in vals):     # (a) NONE of the displayed numbers are spoken
            out.append({"scene": sc.get("id"), "block": sc.get("type"), "n": len(vals),
                        "values": [round(v, 2) for v in vals[:6]]})
    return out


def place_scenes(comp_dir, write: bool = True) -> Dict:
    """Set scene start/dur from where each scene's anchor/text is spoken. Writes back to the specs
    unless ``write=False`` — the `--report` dry-run computes and returns every scene's implied window
    WITHOUT mutating the specs (no recompose, no render), so an author can re-space anchors in
    seconds instead of a full sync→recompose→render iteration (holbein POST_MORTEM #4)."""
    from nolan import aligner
    from nolan.whisper import WordTimestamp
    comp_dir = Path(comp_dir)
    meta = json.loads((comp_dir / "audio_meta.json").read_text(encoding="utf-8"))
    by_frame = {v.get("frame"): v for v in meta.get("voices", [])}
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))
    report = {"frames": [], "fallbacks": 0, "weak_total": 0, "problems": [], "windows": [],
              "number_anchors": [], "selection": []}

    for i, sf in enumerate(spec_files, start=1):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        for fr in spec.get("frames", []):
            scenes = fr.get("scenes", []) or []
            frame_dur = float(fr.get("dur", 0) or 0)
            words_raw = (by_frame.get(i) or {}).get("words") or []
            words = [WordTimestamp(word=w["word"], start=w["start"], end=w["end"]) for w in words_raw]
            stream_tokens = [t for (t, _a, _b) in aligner.flatten_words(words)] if words else []
            fb = None
            weak = []
            unresolved = set()                           # scene ids whose anchor did not match at all
            if not scenes or not words:
                fb = "no words/scenes"
                starts = _proportional(len(scenes), frame_dur) if scenes else []
                unresolved = {sc.get("id") for sc in scenes}
            else:
                q = [{"id": sc.get("id", f"s{j}"), "narration_excerpt": _scene_query(sc)}
                     for j, sc in enumerate(scenes)]
                results, unmatched = aligner.align_scenes_to_audio(q, words)
                by_id = {r.scene_id: r for r in results}
                raw = [getattr(by_id.get(sc.get("id", f"s{j}")), "start_seconds", None)
                       for j, sc in enumerate(scenes)]
                # the aligner PLACES even a zero-confidence anchor (a garbage fuzzy hit) while flagging it
                # in `unmatched` — don't trust that as a fallback; null it so the scene interpolates + reports
                # UNRESOLVED instead. (Number-aware `_phrase_time` is tried first regardless.)
                lowconf = {u.scene_id for u in (unmatched or []) if float(u.confidence) <= 0.0}
                raw = [None if scenes[j].get("id", f"s{j}") in lowconf else raw[j] for j in range(len(scenes))]
                # #2: number-aware placement + interpolation (no all-or-nothing proportional dump)
                starts, resolved = _resolve_scene_starts(scenes, words, frame_dur, raw)
                unresolved = {sc.get("id", f"s{j}") for j, sc in enumerate(scenes)} - resolved
                if len(unresolved) > max(1, len(scenes) // 2):   # majority unplaced → weak frame (report it)
                    fb = f"interpolated ({len(resolved)}/{len(scenes)} anchors resolved)"
                    report["fallbacks"] += 1
                # LOUD: the aligner KNOWS which anchors matched weakly (confidence < 0.8), but a
                # low-confidence-yet-monotonic placement lands silently otherwise — Whisper mis-
                # transcription ('Jevons'→'Jevin's') mis-places a scene with nothing reported.
                weak = [{"scene": u.scene_id, "conf": round(float(u.confidence), 2),
                         "excerpt": (u.narration_excerpt or "")[:48]} for u in (unmatched or [])]
            drift = 0.0
            for j, sc in enumerate(scenes):
                old = float(sc.get("start", 0) or 0)
                sc["start"] = round(starts[j], 3)
                nxt = starts[j + 1] if j + 1 < len(starts) else frame_dur
                sc["dur"] = round(max(0.1, nxt - starts[j]), 3)
                drift = max(drift, abs(sc["start"] - old))
            # #1: relieve any scene squeezed below its readable minimum (borrow slack from roomy neighbours)
            # BEFORE element cues resolve against the window. Runs on the placed scenes; monotonic + in place.
            rel = _relieve_short_windows(scenes, frame_dur)
            report.setdefault("relieved", 0)
            report["relieved"] += rel["fixed"]
            if rel["residual"]:
                report.setdefault("overpacked", []).extend(
                    {"frame": fr.get("id"), **r} for r in rel["residual"])
            for lf in _visual_lag_flags(scenes, words):   # visual-lag / mis-order (drift the eye catches)
                report.setdefault("visual_lag", []).append({"frame": fr.get("id"), **lf})
            for af in _late_anchor_flags(scenes, words):  # #B anchor-quality: anchored to a late/closing phrase
                report.setdefault("late_anchors", []).append({"frame": fr.get("id"), **af})
            for nf in _number_provenance_flags(scenes, words):  # #3 data-viz numbers not spoken → fabrication risk
                report.setdefault("fabricated_numbers", []).append({"frame": fr.get("id"), **nf})
            cues = revs = 0
            for sc in scenes:                        # fire reveals ON the spoken word (or spread — never clustered)
                d = sc.get("data", {}) or {}
                op = d.get("operative")
                if op and words:                     # the operative highlight sweep
                    t = _phrase_time(op, words, after=float(sc.get("start", 0)))
                    if t is not None and sc["start"] <= t < sc["start"] + sc["dur"]:
                        d["cue"] = round(t - sc["start"], 2)
                        cues += 1
                revs += _retime_reveals(sc, d, words)  # spread fixed-offset reveals over the (retimed) window
                revs += _retime_lines(sc, d, words)    # VO-sync each on-screen text LINE to when it's read
            # anchor-lint: per-scene WINDOW + verdict, so degenerate windows are visible BEFORE a render
            # (a mis-heard anchor silently produces a 0.94s or 27s window — this was ~80% of the rework).
            for sc in scenes:
                block, dur = sc.get("type", "?"), float(sc.get("dur", 0) or 0)
                minr = _MIN_READABLE.get(block, 3.0)
                grounded = _scene_media(block, sc.get("data", {}) or {}) != "none"   # document/newshead count
                sid = sc.get("id")
                resolved = sid not in unresolved
                if dur + 1e-6 < minr:
                    v = f"SHORT {dur:.1f}s < {minr:.0f}s (unreadable)"
                elif dur > 8 and not grounded and block not in _MOTION_BLOCKS:
                    v = f"LONG-HOLD {dur:.1f}s ungrounded"
                elif not resolved:
                    v = "UNRESOLVED (anchor not found — placed by fallback)"
                else:
                    v = None
                entry = {"frame": fr.get("id"), "scene": sid, "block": block,
                         "start": round(float(sc.get("start", 0) or 0), 2),
                         "dur": round(dur, 2), "resolved": resolved,
                         "anchor": (_scene_query(sc) or "")[:60], "verdict": v or "ok"}
                if not resolved:                         # ⑤ suggest the verbatim transcript span to anchor to
                    sg = _suggest_anchor_span(_scene_query(sc), stream_tokens)
                    if sg:
                        entry["suggest"] = sg
                aq = _scene_query(sc)
                if _numberish_anchor(aq):                 # ⑥ leads with a number → Whisper writes digits → risky
                    entry["number_anchor"] = True
                    report["number_anchors"].append({"frame": fr.get("id"), "scene": sid, "anchor": aq[:60],
                                                      "resolved": resolved})
                sel = _selection_advice(sc)               # ⑦ structural block-choice mismatch (advisory)
                if sel:
                    entry["selection"] = sel
                    report["selection"].append({"frame": fr.get("id"), "scene": sid, "block": block, "advice": sel})
                report["windows"].append(entry)
                if v:
                    report["problems"].append({"frame": fr.get("id"), "scene": sid,
                                               "block": block, "dur": round(dur, 2), "issue": v})
            if weak:
                report["weak_total"] += len(weak)
                print(f"  ⚠ {fr.get('id')}: {len(weak)} weak anchor(s) (Whisper may have mis-heard) — "
                      + ", ".join(f"{w['scene']}@conf {w['conf']} “{w['excerpt']}”" for w in weak))
            report["frames"].append({"frame": fr.get("id"), "scenes": len(scenes),
                                     "max_shift_s": round(drift, 2), "cues_synced": cues,
                                     "reveals_retimed": revs,
                                     "fallback": fb, "weak_anchors": weak})
        if write:
            sf.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return report


def check_vo_fidelity(comp_dir) -> List[Dict]:
    """④ Flag SOURCE.md sentences the cloned VO DROPPED/garbled — content words absent from the spoken
    transcript. Frame i ↔ SOURCE.md section i (the "narration owns duration" invariant). A silent VO
    omission (homer: a whole sentence gone) makes authoring against the script wrong; surface it early."""
    from nolan.aligner import flatten_words
    from nolan.whisper import WordTimestamp
    from nolan.script import parse_script_sections
    comp_dir = Path(comp_dir)
    src = ""
    for cand in ("SOURCE.md", "SCRIPT.md"):
        p = comp_dir / cand
        if p.exists():
            src = p.read_text(encoding="utf-8")
            break
    sections = parse_script_sections(src) if src else []
    if not sections:
        return []
    meta = json.loads((comp_dir / "audio_meta.json").read_text(encoding="utf-8"))
    by_frame = {v.get("frame"): v for v in meta.get("voices", [])}
    out = []
    for i in range(1, len(sections) + 1):
        words_raw = (by_frame.get(i) or {}).get("words") or []
        words = [WordTimestamp(word=w["word"], start=w["start"], end=w["end"]) for w in words_raw]
        spoken = [t for (t, _a, _b) in flatten_words(words)]
        if not spoken:
            continue
        for d in _dropped_sentences(sections[i - 1].get("body", ""), spoken):
            out.append({"frame": i, **d})
    return out


def visual_lag_report(comp_dir) -> List[Dict]:
    """The visual-lag / mis-order flags for a comp (via the sync dry-run, no write) — the finish DAG's
    pre-render gate consumes this so drift is caught BEFORE the render, not by a human watching the output."""
    try:
        return report_windows(comp_dir).get("visual_lag", []) or []
    except Exception:
        return []


def sync_gate_report(comp_dir) -> Dict:
    """One dry-run for the finish DAG's pre-render SYNC GATE: {visual_lag, late_anchors}. Catches the drift
    class (visual trails the VO / mis-ordered scenes) + anchor-quality (anchored to a late/closing phrase)
    BEFORE the render spend."""
    try:
        r = report_windows(comp_dir)
        return {"visual_lag": r.get("visual_lag", []) or [], "late_anchors": r.get("late_anchors", []) or [],
                "fabricated_numbers": r.get("fabricated_numbers", []) or []}
    except Exception:
        return {"visual_lag": [], "late_anchors": [], "fabricated_numbers": []}


def report_windows(comp_dir) -> Dict:
    """Dry-run preview: align (idempotent, cached) then resolve every scene's implied window WITHOUT
    moving scenes or writing specs — the fast loop for re-spacing anchors (POST_MORTEM #4). Also runs
    the ④ VO↔script fidelity check so a dropped narration line surfaces in the same pass."""
    align_voices(comp_dir)                               # cached by wav mtime; needed for spoken times
    rep = place_scenes(comp_dir, write=False)
    rep["vo_drops"] = check_vo_fidelity(comp_dir)
    return rep


def _validate_monotonic(raw: List[Optional[float]], frame_dur: float) -> Optional[List[float]]:
    """Scene 1 opens the frame (start 0); the rest must resolve to strictly-increasing times inside
    the frame. Any gap or inversion => None (caller falls back to proportional for the frame)."""
    if not raw:
        return None
    out = [0.0]
    prev = 0.0
    for v in raw[1:]:
        if v is None or v <= prev + 0.15 or v >= frame_dur:
            return None
        out.append(round(v, 3))
        prev = v
    return out


def main():
    """python -X utf8 -m nolan.hyperframes.sync <comp> [--align-only]
    Force-align the section wavs, then place each scene on its spoken anchor (recompose + re-render after)."""
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.sync")
    ap.add_argument("comp", help="composition dir (…/videos/<slug>)")
    ap.add_argument("--force", action="store_true", help="re-align even if words already present")
    ap.add_argument("--align-only", action="store_true", help="align the wavs but don't move scenes")
    ap.add_argument("--report", action="store_true",
                    help="DRY-RUN: print per-scene windows + SHORT/LONG/UNRESOLVED flags without "
                         "moving scenes / recompose / render (fast anchor-tuning loop)")
    a = ap.parse_args()

    if a.report:
        rep = report_windows(a.comp)
        cur = None
        for w in rep["windows"]:
            if w["frame"] != cur:
                cur = w["frame"]
                print(f"\n{cur}")
            mark = "✓" if w["verdict"] == "ok" else "✗"
            end = round(w["start"] + w["dur"], 2)
            print(f"  {mark} {w['scene']:>4} [{w['block']:<10}] {w['start']:6.2f}–{end:<6.2f} "
                  f"({w['dur']:>4.1f}s)  {w['verdict']}")
            if w["verdict"] != "ok":
                print(f"           anchor: “{w['anchor']}”")
                if w.get("suggest"):                     # ⑤ the verbatim transcript span to anchor to instead
                    print(f"           ↳ try anchoring to the spoken words: “{w['suggest']}”")
        drops = rep.get("vo_drops") or []
        if drops:                                        # ④ narration the cloned VO dropped/garbled
            print("\n⚠ VO↔script drops (SOURCE lines the voiceover did NOT say — re-synth or re-author):")
            for d in drops:
                print(f"    frame {d['frame']} (cover {d['coverage']:.0%}): “{d['sentence']}”")
        nums = rep.get("number_anchors") or []
        if nums:                                          # ⑥ anchors that lead with a number (Whisper writes digits)
            unresolved_nums = [n for n in nums if not n.get("resolved")]
            print(f"\n⚠ {len(nums)} anchor(s) lead with a NUMBER — Whisper transcribes numbers as digits "
                  f"('nine hundred million'→'900 million'), so these often mis-match. Prefer a nearby "
                  f"non-numeric span{'; these did NOT resolve:' if unresolved_nums else ' (verify the '+str(len(nums))+'):'}")
            for n in (unresolved_nums or nums):
                print(f"    {n['frame']}/{n['scene']}: “{n['anchor']}”")
        sels = rep.get("selection") or []
        if sels:                                          # ⑦ structural block-choice mismatches (advisory)
            print("\n⚠ block selection — the data suggests a better-fitting block (advisory, not a gate):")
            for sdv in sels:
                print(f"    {sdv['frame']}/{sdv['scene']} ({sdv['block']}): {sdv['advice']}")
        lags = rep.get("visual_lag") or []
        if lags:                                          # visual lags the VO (late anchor / mis-ordered scene)
            print("\n⚠ visual-lag — the VISUAL trails the narration (the eye catches this drift):")
            for lf in lags:
                if lf["kind"] == "lag":
                    print(f"    {lf['frame']}/{lf['scene']} ({lf['block']}) placed @{lf['start']}s but its "
                          f"content is spoken @{lf['content_at']}s — LAG {lf['lag']}s (a late anchor; the "
                          f"previous scene overruns). Anchor it to an EARLIER phrase.")
                else:
                    print(f"    {lf['frame']}/{lf['scene']} ({lf['block']}) topic narrated @{lf['content_at']}s, "
                          f"BEFORE the previous scene's @{lf['prev_content_at']}s — scenes are OUT OF ORDER "
                          f"for the VO; reorder them in the spec.")
        fab = rep.get("fabricated_numbers") or []
        if fab:                                           # #3 data-viz numbers absent from the narration
            print("\n⚠ number provenance — these data blocks show numbers spoken NOWHERE in the narration "
                  "(a fabrication risk — the block may have invented data the script never gave; source them "
                  "or use a non-quantitative block):")
            for nf in fab:
                print(f"    {nf['frame']}/{nf['scene']} ({nf['block']}) shows {nf['n']} numbers "
                      f"{nf['values']} — none are spoken in the frame's VO")
        lates = rep.get("late_anchors") or []
        if lates:                                         # #B anchor-quality — anchored to a late/closing phrase
            print("\n◆ anchor-quality — these scenes are anchored to a LATE/closing phrase (placement "
                  "auto-corrects via content, but re-anchor to the OPENING for robustness):")
            for af in lates:
                print(f"    {af['frame']}/{af['scene']} ({af['block']}): anchor {af['anchor']!r} is spoken "
                      f"@{af['anchor_at']}s but the topic opens @{af['content_at']}s")
        over = rep.get("overpacked") or []
        if over:                                          # #1: frames too packed for the reliever to satisfy
            print("\n⚠ over-packed windows — the reliever grew them as far as neighbours allowed, but these "
                  "are still under their readable floor (too many scenes for the frame; cut or merge one):")
            for o in over:
                print(f"    {o['frame']}/{o['scene']} ({o['block']}) — {o['dur']}s < {o['min']}s floor")
        probs = rep.get("problems") or []
        print(f"\n— {len(rep['windows'])} scene(s); {len(probs)} degenerate window(s); "
              f"{rep['fallbacks']} frame(s) weak-placed; {rep.get('relieved', 0)} short window(s) relieved; "
              f"{len(over)} over-packed; {rep['weak_total']} weak anchor(s); "
              f"{len(nums)} number-anchor(s); {len(sels)} selection advisory(ies); {len(drops)} VO drop(s)")
        print("  (dry-run — specs unchanged. Fix anchors, re-run --report, then `sync` to commit + recompose.)")
        return

    print("ALIGN:", _json.dumps(align_voices(a.comp, force=a.force)))
    if not a.align_only:
        rep = place_scenes(a.comp)
        for f in rep["frames"]:
            print(f"  {f['frame']:14} scenes={f['scenes']} max_shift={f['max_shift_s']}s "
                  f"cues={f['cues_synced']} fallback={f['fallback']}")
        print(f"fallbacks: {rep['fallbacks']} frame(s) — add `anchor` to those scenes for word-accurate placement")
        if rep.get("weak_total"):
            print(f"⚠ weak anchors: {rep['weak_total']} scene(s) matched at low confidence — verify their "
                  f"placement (Whisper may have mis-transcribed the anchor phrase); see weak_anchors per frame")
        probs = rep.get("problems") or []
        if probs:
            print(f"\n✗ ANCHOR-LINT: {len(probs)} window problem(s) — FIX BEFORE RENDER "
                  f"(a mis-heard anchor silently made these):")
            for p in probs:
                print(f"    {p['frame']}/{p['scene']} ({p['block']}) — {p['issue']}")
        else:
            print("anchor-lint: all scene windows readable ✓")


if __name__ == "__main__":
    main()

