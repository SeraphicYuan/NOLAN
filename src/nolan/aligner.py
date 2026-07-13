"""Audio-to-scene alignment using word-level timestamps."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from nolan.whisper import WordTimestamp, WhisperTranscriber, WhisperConfig


def normalize_text(text: str) -> str:
    """Normalize text for matching (lowercase, remove punctuation, handle accents)."""
    # Normalize unicode (é → e, ñ → n, etc.)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    text = text.lower()

    # Replace common special characters
    text = text.replace('—', ' ')  # em dash
    text = text.replace('–', ' ')  # en dash
    text = text.replace(''', "'")  # curly quote
    text = text.replace(''', "'")
    text = text.replace('"', '"')
    text = text.replace('"', '"')

    # Remove all punctuation
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def words_to_text(words: List[WordTimestamp]) -> str:
    """Convert word list to normalized text."""
    return normalize_text(' '.join(w.word for w in words))


def flatten_words(words: List[WordTimestamp]) -> List[Tuple[str, float, float]]:
    """Flatten whisper words into a token-level stream ``[(token, start, end)]``.

    A hyphenated / possessive / punctuated whisper word contributes ALL its sub-tokens
    ('forty-one' -> forty, one; "bishop's" -> bishop, s), with timing interpolated across the
    sub-tokens by character length. ``normalize_text`` already splits on punctuation, so one word
    yields 0, 1, or N tokens. Both sides of a match MUST tokenize this way (or via
    ``normalize_text().split()``) — otherwise a multi-token word silently drops its tail and the
    anchor misses (holbein POST_MORTEM #5). For a single-token word this is an identity: one token
    at the word's own start/end, so all existing single-token behavior is preserved."""
    out: List[Tuple[str, float, float]] = []
    for w in words:
        toks = normalize_text(w.word).split()
        if not toks:
            continue
        start, end = float(w.start), float(w.end)
        span = max(0.0, end - start)
        total = sum(len(t) for t in toks) or 1
        acc = 0
        for t in toks:
            ts = start + span * (acc / total)
            acc += len(t)
            te = start + span * (acc / total)
            out.append((t, round(ts, 4), round(te, 4)))
    return out


def find_text_in_words(
    query: str,
    words: List[WordTimestamp],
    start_index: int = 0,
    fuzzy_threshold: float = 0.5,  # Lowered from 0.8
) -> Optional[Tuple[int, int, float]]:
    """Find query text in word list, return (start_idx, end_idx, confidence).

    Args:
        query: Text to find.
        words: List of word timestamps.
        start_index: Start searching from this index.
        fuzzy_threshold: Minimum similarity for fuzzy match.

    Returns:
        Tuple of (start_word_index, end_word_index, confidence) or None.

    Internally matches on a FLATTENED token stream (see :func:`flatten_words`) so a
    hyphenated/possessive whisper word contributes all its sub-tokens instead of collapsing to one
    slot (else 'forty-one'->'forty' silently dropped 'one' and the anchor missed — POST_MORTEM #5).
    Token indices are mapped back to source WORD indices, so the return contract is unchanged and
    callers can still slice ``words`` / read ``words[idx].start``.
    """
    query_normalized = normalize_text(query)
    query_words = query_normalized.split()

    if not query_words:
        return None

    # Flatten to a single-token-per-slot stream, keeping a map back to the source word index.
    tokens: list = []
    tok2word: list = []
    for wi, w in enumerate(words):
        for t in normalize_text(w.word).split():
            tokens.append(t)
            tok2word.append(wi)
    if not tokens:
        return None

    # start_index is a WORD index -> first token at/after it.
    start_tok = next((ti for ti, wi in enumerate(tok2word) if wi >= start_index), len(tokens))
    n = len(query_words)

    def _to_words(ts: int, te: int, conf: float):
        sw = tok2word[ts]
        ew = tok2word[min(te, len(tokens)) - 1] + 1 if te > ts else sw + 1
        return (sw, ew, conf)

    # Sliding window search for exact match
    for i in range(start_tok, len(tokens) - min(n, len(tokens) - start_tok) + 1):
        window_size = min(n, len(tokens) - i)
        if ' '.join(tokens[i:i + window_size]) == query_normalized:
            return _to_words(i, i + n, 1.0)

    # Check first few words match (for partial matches). A bare 2-word
    # prefix is NOT evidence — "It is…" matched a scene 46s late in the
    # aeneid-2beat-v2 run and, because the search cursor only moves forward,
    # starved every later scene. The expansion must confirm the match
    # (>= half the query, or it isn't this sentence).
    for i in range(start_tok, len(tokens)):
        first_words = min(2, n)
        first_query = ' '.join(query_words[:first_words])

        if i + first_words > len(tokens):
            continue

        if first_query == ' '.join(tokens[i:i + first_words]):
            best_end = i + first_words
            matched_count = first_words

            for j in range(first_words, min(n * 2, len(tokens) - i)):
                if i + j >= len(tokens):
                    break
                if j < n and tokens[i + j] == query_words[j]:
                    matched_count += 1
                    best_end = i + j + 1
                elif j >= n:
                    break

            confidence = matched_count / n
            if confidence >= fuzzy_threshold:
                return _to_words(i, best_end, min(1.0, confidence))
            # prefix-only hit: keep scanning; the fuzzy pass below may still
            # find a REAL occurrence later in the stream

    # Fuzzy fallback: find best partial match starting with first word
    best_match = None
    best_score = 0

    for i in range(start_tok, len(tokens)):
        first_word_match = (
            tokens[i] == query_words[0] or
            query_words[0].startswith(tokens[i]) or
            tokens[i].startswith(query_words[0])
        )

        if first_word_match:
            matches = 1
            end_idx = i + 1
            query_idx = 1

            while query_idx < n and end_idx < len(tokens):
                if tokens[end_idx] == query_words[query_idx]:
                    matches += 1
                    query_idx += 1
                elif query_idx + 1 < n and tokens[end_idx] == query_words[query_idx + 1]:
                    # Skip a word in query (might be filler)
                    query_idx += 2
                    matches += 1
                else:
                    # Allow one mismatch, continue
                    pass
                end_idx += 1

                if end_idx - i > n * 1.5:
                    break

            score = matches / n
            if score > best_score and score >= fuzzy_threshold:
                best_score = score
                best_match = _to_words(i, end_idx, score)

    return best_match


@dataclass
class AlignmentResult:
    """Result of aligning a scene to audio."""
    scene_id: str
    start_seconds: float
    end_seconds: float
    confidence: float
    matched_text: str
    narration_excerpt: str = ""  # Original excerpt for logging


def align_scenes_to_audio(
    scenes: List[dict],
    words: List[WordTimestamp],
) -> Tuple[List[AlignmentResult], List[AlignmentResult]]:
    """Align scene narration excerpts to word timestamps.

    Args:
        scenes: List of scene dicts with 'id' and 'narration_excerpt'.
        words: List of word timestamps from Whisper.

    Returns:
        Tuple of (all_alignments, unmatched_alignments).
    """
    results = []
    unmatched = []
    current_word_idx = 0

    for i, scene in enumerate(scenes):
        scene_id = scene.get('id', f'scene_{i}')
        narration = scene.get('narration_excerpt', '')

        if not narration:
            continue

        # Find this narration in the word stream
        match = find_text_in_words(narration, words, current_word_idx)

        if match:
            start_idx, end_idx, confidence = match
            start_time = words[start_idx].start
            end_time = words[min(end_idx - 1, len(words) - 1)].end
            matched_text = ' '.join(w.word for w in words[start_idx:end_idx])

            result = AlignmentResult(
                scene_id=scene_id,
                start_seconds=start_time,
                end_seconds=end_time,
                confidence=confidence,
                matched_text=matched_text,
                narration_excerpt=narration,
            )
            results.append(result)

            # Track low confidence as partial unmatched
            if confidence < 0.8:
                unmatched.append(result)

            # Move search window forward
            current_word_idx = end_idx
        else:
            # No match found, estimate based on position
            prev_end = results[-1].end_seconds if results else 0.0
            result = AlignmentResult(
                scene_id=scene_id,
                start_seconds=prev_end,
                end_seconds=prev_end,  # Will be updated by next scene
                confidence=0.0,
                matched_text='',
                narration_excerpt=narration,
            )
            results.append(result)
            unmatched.append(result)

    # Fix end times for scenes with 0 confidence (no match)
    for i in range(len(results) - 1):
        if results[i].end_seconds == results[i].start_seconds:
            results[i].end_seconds = results[i + 1].start_seconds

    # Last scene ends at audio end
    if results and words:
        results[-1].end_seconds = max(results[-1].end_seconds, words[-1].end)

    return results, unmatched


def transcribe_and_align(
    audio_path: Path,
    scenes: List[dict],
    model_size: str = 'base',
    language: Optional[str] = None,
    progress_callback=None,
) -> Tuple[List[WordTimestamp], List[AlignmentResult], List[AlignmentResult]]:
    """Transcribe audio and align scenes.

    Args:
        audio_path: Path to audio file.
        scenes: List of scene dicts.
        model_size: Whisper model size.
        language: Language code or None for auto.
        progress_callback: Optional callback(phase, progress).

    Returns:
        Tuple of (words, alignments, unmatched).
    """
    # Try CUDA first, fall back to CPU
    try:
        config = WhisperConfig(
            model_size=model_size,
            device='cuda',
            compute_type='float16',
            language=language,
        )
        transcriber = WhisperTranscriber(config)

        if progress_callback:
            progress_callback('transcribing', 0.0)

        def on_progress(p):
            if progress_callback:
                progress_callback('transcribing', p)

        words = transcriber.transcribe_words(audio_path, on_progress)

    except Exception:
        # Fall back to CPU
        config = WhisperConfig(
            model_size=model_size,
            device='cpu',
            compute_type='int8',
            language=language,
        )
        transcriber = WhisperTranscriber(config)

        if progress_callback:
            progress_callback('transcribing', 0.0)

        def on_progress(p):
            if progress_callback:
                progress_callback('transcribing', p)

        words = transcriber.transcribe_words(audio_path, on_progress)

    if progress_callback:
        progress_callback('aligning', 0.0)

    alignments, unmatched = align_scenes_to_audio(scenes, words)

    if progress_callback:
        progress_callback('aligning', 1.0)

    return words, alignments, unmatched


def save_word_timestamps(words: List[WordTimestamp], output_path: Path) -> None:
    """Save word timestamps to JSON file."""
    import json

    data = {
        'word_count': len(words),
        'duration': words[-1].end if words else 0,
        'words': [
            {
                'word': w.word,
                'start': round(w.start, 3),
                'end': round(w.end, 3),
                'probability': round(w.probability, 3),
            }
            for w in words
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_unmatched_scenes(unmatched: List[AlignmentResult], output_path: Path) -> None:
    """Save unmatched/low-confidence alignments to JSON for review."""
    import json

    data = {
        'count': len(unmatched),
        'description': 'Scenes with no match (confidence=0) or low confidence (<80%)',
        'scenes': [
            {
                'scene_id': u.scene_id,
                'confidence': round(u.confidence * 100, 1),
                'narration_excerpt': u.narration_excerpt,
                'matched_text': u.matched_text,
                'estimated_start': round(u.start_seconds, 2),
                'estimated_end': round(u.end_seconds, 2),
                'status': 'no_match' if u.confidence == 0 else 'low_confidence',
            }
            for u in unmatched
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
