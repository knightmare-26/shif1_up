/**
 * Live timing is parked. FastF1 only serves a session after it has finished, so the Live pages can't show
 * anything mid-session yet (see CLAUDE.md, "WebSocket live data flow"). While this is false, /live and
 * /live-monitor show a "coming soon" notice; the live code is untouched, so flipping it back is all it takes.
 */
export const LIVE_TIMING_ENABLED = false;
