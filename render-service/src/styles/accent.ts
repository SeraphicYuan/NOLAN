/**
 * Accent Resolution System
 *
 * Parses text with accent markup and enforces style rules.
 * Supports: **markup**, explicit word arrays, and auto-detection.
 */

import type {
  EssayStyle,
  TextSegment,
  AccentedTextInput,
  AccentedText,
  AccentTarget,
} from './types.js';

/**
 * Parse **double asterisk** markup into segments
 */
function parseMarkup(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  const regex = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Text before the match
    if (match.index > lastIndex) {
      segments.push({
        text: text.slice(lastIndex, match.index),
        accent: false,
      });
    }
    // The accented text (without asterisks)
    segments.push({
      text: match[1],
      accent: true,
    });
    lastIndex = regex.lastIndex;
  }

  // Remaining text after last match
  if (lastIndex < text.length) {
    segments.push({
      text: text.slice(lastIndex),
      accent: false,
    });
  }

  // If no markup found, return whole text as non-accented
  if (segments.length === 0) {
    segments.push({ text, accent: false });
  }

  return segments;
}

/**
 * Apply explicit accent to specific words
 */
function applyExplicitAccent(text: string, words: string[]): TextSegment[] {
  if (words.length === 0) {
    return [{ text, accent: false }];
  }

  const segments: TextSegment[] = [];
  const lowerWords = words.map((w) => w.toLowerCase());

  // Split by whitespace but keep delimiters
  const tokens = text.split(/(\s+)/);

  for (const token of tokens) {
    const stripped = token.replace(/[.,!?;:'"()]/g, '').toLowerCase();
    const shouldAccent = lowerWords.includes(stripped);

    if (segments.length > 0 && segments[segments.length - 1].accent === shouldAccent) {
      // Merge with previous segment if same accent state
      segments[segments.length - 1].text += token;
    } else {
      segments.push({ text: token, accent: shouldAccent });
    }
  }

  return segments;
}

/**
 * Check if a word matches an accent target pattern
 */
function matchesTarget(word: string, target: AccentTarget): boolean {
  const cleaned = word.replace(/[.,!?;:'"()]/g, '');

  switch (target) {
    case 'numbers':
      return /^\d+$/.test(cleaned);
    case 'percentages':
      return /^\d+%$/.test(cleaned) || /^\d+\.\d+%$/.test(cleaned);
    case 'money':
      return /^\$[\d,]+(\.\d{2})?$/.test(cleaned) || /^[\d,]+\s?(million|billion|trillion)$/i.test(cleaned);
    case 'dates':
      return /^\d{4}$/.test(cleaned) || // year
             /^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(cleaned) || // date
             /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i.test(cleaned);
    case 'caps':
      return cleaned.length > 1 && cleaned === cleaned.toUpperCase() && /[A-Z]/.test(cleaned);
    case 'first_word':
    case 'last_word':
    case 'quotes':
      return false; // handled separately
    case 'explicit_only':
      return false; // only markup works
    default:
      return false;
  }
}

/**
 * Auto-detect words to accent based on style rules
 */
function autoAccent(text: string, style: EssayStyle, isTitle: boolean): TextSegment[] {
  const maxWords = isTitle
    ? style.accentUsage.maxWordsPerTitle
    : style.accentUsage.maxWordsPerBody;
  const targets = style.accentUsage.allowedTargets;

  // If only explicit markup allowed, return unaccented
  if (targets.length === 1 && targets[0] === 'explicit_only') {
    return [{ text, accent: false }];
  }

  const segments: TextSegment[] = [];
  const tokens = text.split(/(\s+)/);
  let accentedCount = 0;

  // Handle first_word and last_word targets
  const wordTokens = tokens.filter((t) => t.trim().length > 0);
  const firstWord = wordTokens[0]?.replace(/[.,!?;:'"()]/g, '').toLowerCase();
  const lastWord = wordTokens[wordTokens.length - 1]?.replace(/[.,!?;:'"()]/g, '').toLowerCase();

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    const cleaned = token.replace(/[.,!?;:'"()]/g, '').toLowerCase();

    let shouldAccent = false;

    if (accentedCount < maxWords && token.trim().length > 0) {
      // Check each target type
      for (const target of targets) {
        if (target === 'first_word' && cleaned === firstWord) {
          shouldAccent = true;
          break;
        }
        if (target === 'last_word' && cleaned === lastWord) {
          shouldAccent = true;
          break;
        }
        if (matchesTarget(token, target)) {
          shouldAccent = true;
          break;
        }
      }
    }

    if (shouldAccent) {
      accentedCount++;
    }

    if (segments.length > 0 && segments[segments.length - 1].accent === shouldAccent) {
      segments[segments.length - 1].text += token;
    } else {
      segments.push({ text: token, accent: shouldAccent });
    }
  }

  return segments;
}

/**
 * Count accented words in segments
 */
function countAccentedWords(segments: TextSegment[]): number {
  return segments
    .filter((s) => s.accent)
    .reduce((count, seg) => {
      const words = seg.text.trim().split(/\s+/).filter((w) => w.length > 0);
      return count + words.length;
    }, 0);
}

/**
 * Validate accent usage against style rules
 */
function validateAccent(
  segments: TextSegment[],
  style: EssayStyle,
  isTitle: boolean
): { valid: boolean; error?: string } {
  const accentCount = countAccentedWords(segments);
  const maxAllowed = isTitle
    ? style.accentUsage.maxWordsPerTitle
    : style.accentUsage.maxWordsPerBody;

  if (accentCount > maxAllowed) {
    return {
      valid: false,
      error: `Too many accented words: ${accentCount} > ${maxAllowed} (${isTitle ? 'title' : 'body'})`,
    };
  }

  // Check forbidden patterns
  const accentedText = segments
    .filter((s) => s.accent)
    .map((s) => s.text)
    .join(' ')
    .toLowerCase();

  for (const pattern of style.accentUsage.forbiddenPatterns) {
    if (accentedText.includes(pattern.toLowerCase())) {
      return {
        valid: false,
        error: `Forbidden accent pattern: "${pattern}"`,
      };
    }
  }

  return { valid: true };
}

/**
 * Main accent resolution function
 *
 * @param input - Text with optional accent hints
 * @param style - The essay style with accent rules
 * @param isTitle - Whether this is title text (stricter rules)
 * @returns Resolved text segments with accent information
 * @throws Error if accent rules are violated
 */
export function resolveAccent(
  input: AccentedTextInput,
  style: EssayStyle,
  isTitle: boolean = false
): AccentedText {
  let segments: TextSegment[];

  // Priority: explicit array > inline markup > auto > none
  if (input.accent === 'none') {
    segments = [{ text: input.text, accent: false }];
  } else if (Array.isArray(input.accent)) {
    segments = applyExplicitAccent(input.text, input.accent);
  } else if (input.text.includes('**')) {
    segments = parseMarkup(input.text);
  } else if (input.accent === 'auto') {
    segments = autoAccent(input.text, style, isTitle);
  } else {
    // Default: try markup, then auto
    if (input.text.includes('**')) {
      segments = parseMarkup(input.text);
    } else {
      segments = autoAccent(input.text, style, isTitle);
    }
  }

  // Validate against style rules
  const validation = validateAccent(segments, style, isTitle);
  if (!validation.valid) {
    throw new Error(validation.error);
  }

  // Clean up: merge adjacent segments with same accent state
  const merged: TextSegment[] = [];
  for (const seg of segments) {
    if (merged.length > 0 && merged[merged.length - 1].accent === seg.accent) {
      merged[merged.length - 1].text += seg.text;
    } else {
      merged.push({ ...seg });
    }
  }

  return {
    segments: merged,
    accentCount: countAccentedWords(merged),
    raw: input.text,
  };
}

/**
 * Simple helper to get plain text with markup stripped
 */
export function stripAccentMarkup(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '$1');
}

/**
 * Check if text contains accent markup
 */
export function hasAccentMarkup(text: string): boolean {
  return /\*\*[^*]+\*\*/.test(text);
}

/**
 * Apply accent color to segments for rendering
 */
export function colorizeSegments(
  segments: TextSegment[],
  style: EssayStyle
): Array<{ text: string; color: string }> {
  return segments.map((seg) => ({
    text: seg.text,
    color: seg.accent ? style.colors.accent : style.colors.primaryText,
  }));
}
