/**
 * Styles API Routes
 *
 * Endpoints for querying available styles.
 */

import { Router, Request, Response } from 'express';
import {
  getStyle,
  getStyleIds,
  getStyleSummaries,
  resolveAccent,
  STYLES,
} from '../styles/index.js';

const router = Router();

/**
 * GET /styles
 * List all available styles
 */
router.get('/', (_req: Request, res: Response) => {
  res.json({
    styles: getStyleSummaries(),
    default: 'noir-essay',
  });
});

/**
 * GET /styles/:id
 * Get full style definition
 */
router.get('/:id', (req: Request, res: Response) => {
  const id = req.params.id as string;

  if (!STYLES[id]) {
    res.status(404).json({ error: `Style not found: ${id}` });
    return;
  }

  res.json(STYLES[id]);
});

/**
 * POST /styles/:id/resolve-accent
 * Test accent resolution with a style
 *
 * Body: { text: string, accent?: 'auto' | 'none' | string[], isTitle?: boolean }
 */
router.post('/:id/resolve-accent', (req: Request, res: Response) => {
  const id = req.params.id as string;
  const { text, accent, isTitle } = req.body;

  if (!STYLES[id]) {
    res.status(404).json({ error: `Style not found: ${id}` });
    return;
  }

  if (!text || typeof text !== 'string') {
    res.status(400).json({ error: 'Missing required field: text' });
    return;
  }

  const style = getStyle(id);

  try {
    const result = resolveAccent({ text, accent }, style, isTitle ?? false);
    res.json({
      style: id,
      input: { text, accent, isTitle },
      result: {
        segments: result.segments,
        accentCount: result.accentCount,
        colors: result.segments.map((seg) => ({
          text: seg.text,
          color: seg.accent ? style.colors.accent : style.colors.primaryText,
        })),
      },
    });
  } catch (error) {
    res.status(400).json({
      error: error instanceof Error ? error.message : 'Accent resolution failed',
    });
  }
});

/**
 * POST /styles/:id/preview
 * Generate a preview of how content would look with a style
 *
 * Body: { title?: string, body?: string }
 */
router.post('/:id/preview', (req: Request, res: Response) => {
  const id = req.params.id as string;
  const { title, body } = req.body;

  if (!STYLES[id]) {
    res.status(404).json({ error: `Style not found: ${id}` });
    return;
  }

  const style = getStyle(id);

  // Sample content if not provided (respects most restrictive style limits)
  const sampleTitle = title || 'The **Hidden** Truth';
  const sampleBody = body || 'In 2023, the market shifted dramatically, affecting over **73%** of investors.';

  try {
    const titleResult = resolveAccent({ text: sampleTitle }, style, true);
    const bodyResult = resolveAccent({ text: sampleBody }, style, false);

    res.json({
      style: {
        id: style.id,
        name: style.name,
        description: style.description,
      },
      colors: {
        background: style.colors.background,
        primaryText: style.colors.primaryText,
        secondaryText: style.colors.secondaryText,
        accent: style.colors.accent,
        muted: style.colors.muted,
      },
      typography: {
        titleFont: style.typography.titleFont,
        bodyFont: style.typography.bodyFont,
        titleWeight: style.typography.titleWeight,
        bodyWeight: style.typography.bodyWeight,
        case: style.typography.case,
      },
      textSizes: style.textScale1080p,
      texture: {
        grainOpacity: style.texture.grainOpacity,
        vignette: style.texture.vignette,
        hasGradient: style.texture.gradient !== null,
      },
      preview: {
        title: {
          raw: sampleTitle,
          segments: titleResult.segments.map((seg) => ({
            text: seg.text,
            color: seg.accent ? style.colors.accent : style.colors.primaryText,
          })),
          accentCount: titleResult.accentCount,
        },
        body: {
          raw: sampleBody,
          segments: bodyResult.segments.map((seg) => ({
            text: seg.text,
            color: seg.accent ? style.colors.accent : style.colors.primaryText,
          })),
          accentCount: bodyResult.accentCount,
        },
      },
    });
  } catch (error) {
    res.status(400).json({
      error: error instanceof Error ? error.message : 'Preview generation failed',
    });
  }
});

export default router;
