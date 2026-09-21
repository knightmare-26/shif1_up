// Livery colours, matched on the team name each data source happens to use
// ("Red Bull", "Red Bull Racing", "RB F1 Team", "Alpine F1 Team", ...).
const TEAM_COLORS: [RegExp, string][] = [
  [/red bull/i, '#3671C6'],
  [/racing bulls|^rb\b|visa|alphatauri|toro rosso/i, '#6692FF'],
  [/ferrari/i, '#E8002D'],
  [/mercedes/i, '#27F4D2'],
  [/mclaren/i, '#FF8000'],
  [/aston/i, '#229971'],
  [/alpine/i, '#FF87BC'],
  [/williams/i, '#64C4FF'],
  [/audi/i, '#F50537'],
  [/sauber|stake|alfa/i, '#52E252'],
  [/haas/i, '#B6BABD'],
  [/cadillac/i, '#C8CCCE'],
];

const FALLBACK = '#6B7280';

export const teamColor = (name?: string | null): string => {
  if (!name) return FALLBACK;
  return TEAM_COLORS.find(([re]) => re.test(name))?.[1] ?? FALLBACK;
};
