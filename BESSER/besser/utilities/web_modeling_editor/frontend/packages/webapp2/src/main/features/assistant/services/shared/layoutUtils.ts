/**
 * Default layout grid constants shared between converters and services.
 * Single source of truth -- do not duplicate these values elsewhere.
 *
 * Coordinates are calibrated to the BESSER canvas default viewport.
 * Reference: Library example places classes at x∈[-710, 290], y∈[-380, -150].
 */

/** Number of columns in the layout grid. */
export const LAYOUT_COLUMNS = 3;

/** Horizontal distance between column origins. */
export const LAYOUT_H_GAP = 280;

/** Vertical distance between row origins. */
export const LAYOUT_V_GAP = 240;

/** Default X-origin for the layout grid (first class top-left). */
export const LAYOUT_START_X = -440;

/** Default Y-origin for the layout grid (first class top-left). */
export const LAYOUT_START_Y = -380;

/** Calculate grid position for element at the given index. */
export function calculateGridPosition(index: number): { x: number; y: number } {
  const col = index % LAYOUT_COLUMNS;
  const row = Math.floor(index / LAYOUT_COLUMNS);
  return {
    x: LAYOUT_START_X + col * LAYOUT_H_GAP,
    y: LAYOUT_START_Y + row * LAYOUT_V_GAP,
  };
}

