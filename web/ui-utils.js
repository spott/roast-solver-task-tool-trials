export function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "Not reached";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m} min`;
}
export function tempColor(t, target = 60) {
  if (!Number.isFinite(t)) return [18, 22, 24, 0];
  const stops = [[0, 31, 65, 99], [0.55, 42, 157, 143], [0.78, 244, 183, 72], [1, 194, 57, 52]];
  const q = Math.max(0, Math.min(1, (t - 5) / Math.max(target + 20 - 5, 1)));
  let b = stops[stops.length - 1], a = stops[0];
  for (let i = 1; i < stops.length; i++) if (q <= stops[i][0]) { a = stops[i - 1]; b = stops[i]; break; }
  const f = (q - a[0]) / (b[0] - a[0] || 1);
  return [Math.round(a[1] + f * (b[1] - a[1])), Math.round(a[2] + f * (b[2] - a[2])), Math.round(a[3] + f * (b[3] - a[3])), 255];
}
export function historyRows(flat) {
  const rows = [];
  for (let i = 0; i + 2 < flat.length; i += 3) rows.push({ time: flat[i], cold: flat[i + 1], probe: flat[i + 2] });
  return rows;
}
export function presetId(name) { return ({ roast: 0, bird: 1, slab: 2, ham: 3 })[name] ?? 0; }
