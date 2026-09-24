/** "38%", "<1%", ">99%" — a simulation can't honestly claim more precision than that. */
export function formatChance(p: number): string {
  if (p <= 0) return '0%';
  if (p < 0.01) return '<1%';
  if (p > 0.99 && p < 1) return '>99%';
  return `${Math.round(p * 100)}%`;
}
