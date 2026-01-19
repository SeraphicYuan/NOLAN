/**
 * Assets API Routes
 *
 * Endpoints for retrieving visual assets (icons, shapes) used in motion effects.
 */

import { Router, Request, Response } from 'express';
import { assetManager, EMBEDDED_ICONS } from '../assets/index.js';

const router = Router();

// Helper to extract string from query param (handles array case)
function queryString(value: unknown): string | undefined {
  if (typeof value === 'string') return value;
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  return undefined;
}

/**
 * GET /assets/icons
 * List all available icons
 */
router.get('/icons', (_req: Request, res: Response) => {
  const styleId = queryString(_req.query.style);
  const icons = assetManager.listIcons(styleId);

  res.json({
    count: icons.length,
    icons: icons,
    embedded_count: Object.keys(EMBEDDED_ICONS).length,
  });
});

/**
 * GET /assets/icons/:name
 * Get icon SVG content
 *
 * Query params:
 * - style: Style ID for style-specific icons
 * - variant: Variant suffix (e.g., "ribbon" for "arrow-ribbon.svg")
 * - color: Color to replace currentColor
 * - format: "svg" (default) or "json"
 */
router.get('/icons/:name', (req: Request, res: Response) => {
  const name = String(req.params.name);
  const styleId = queryString(req.query.style);
  const variant = queryString(req.query.variant);
  const color = queryString(req.query.color);
  const format = queryString(req.query.format);

  const svg = assetManager.getIcon(name, styleId, variant, color);

  if (!svg) {
    return res.status(404).json({
      error: 'Icon not found',
      name,
      available: assetManager.listIcons(styleId).slice(0, 10),
    });
  }

  if (format === 'json') {
    return res.json({
      name,
      style: styleId || null,
      variant: variant || null,
      svg,
    });
  }

  // Return SVG directly
  res.setHeader('Content-Type', 'image/svg+xml');
  res.send(svg);
});

/**
 * GET /assets/variants/:styleId/*
 * List available variants for an asset
 */
router.get('/variants/:styleId/*', (req: Request, res: Response) => {
  const styleId = String(req.params.styleId);
  const assetName = String(req.params[0]); // Everything after styleId/

  const variants = assetManager.listVariants(styleId, assetName);

  res.json({
    styleId,
    assetName,
    variants,
    count: variants.length,
  });
});

/**
 * GET /assets/check/:styleId/:assetName
 * Check if an asset exists
 */
router.get('/check/:styleId/*', (req: Request, res: Response) => {
  const styleId = String(req.params.styleId);
  const assetName = String(req.params[0]); // Everything after styleId/
  const variant = queryString(req.query.variant);

  const assetPath = assetManager.getAssetPath(styleId, assetName, variant);

  res.json({
    exists: assetPath !== null,
    styleId,
    assetName,
    variant: variant || null,
    path: assetPath,
  });
});

export default router;
