// Schedule dates are plain calendar days ("2026-09-26"). Parsing them with
// `new Date(str)` treats them as UTC midnight, which drifts a day in most
// timezones — so everything here works on the local calendar day instead.

const pad = (n: number) => String(n).padStart(2, '0');

/** Today as YYYY-MM-DD in the viewer's local timezone. */
export const todayISO = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

/** True once the race's calendar day has ended (a race happening today isn't past yet). */
export const isPastDate = (iso: string): boolean => !!iso && iso.slice(0, 10) < todayISO();

export const parseISODate = (iso: string): Date | null => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
};

/** "26 Sep 2026", or "—" when the date is missing/invalid. */
export const formatDate = (iso: string): string => {
  const d = parseISODate(iso);
  return d
    ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : '—';
};

/** Whole days from today until `iso` (0 = today, negative = past). */
export const daysUntil = (iso: string): number | null => {
  const d = parseISODate(iso);
  if (!d) return null;
  const t = parseISODate(todayISO())!;
  return Math.round((d.getTime() - t.getTime()) / 86_400_000);
};

export const describeDaysUntil = (days: number | null): string => {
  if (days === null) return '';
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  return days > 0 ? `In ${days} days` : `${-days} days ago`;
};
