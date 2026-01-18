import * as fs from 'fs';

/**
 * Common utilities shared across rendering engines.
 */

/**
 * Ensure a directory exists, creating it recursively if needed.
 */
export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

/**
 * Safely convert a value to a number, returning a fallback if invalid.
 */
export function toNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/**
 * Safely convert a value to a non-empty string, returning a fallback if invalid.
 */
export function toString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback;
}

/**
 * Safely convert a value to a boolean, returning a fallback if invalid.
 */
export function toBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    if (value.toLowerCase() === 'true') return true;
    if (value.toLowerCase() === 'false') return false;
  }
  return fallback;
}
