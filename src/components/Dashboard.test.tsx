import { leadOver } from './Dashboard';

test("the leader card names the gap to second place, not a bare '+84 on P2'", () => {
  expect(leadOver(320, 236, 'George Russell', false)).toBe('84 ahead of George Russell');
  expect(leadOver(437, 374.5, 'Lando Norris', true)).toBe('won by 62.5 over Lando Norris');
  expect(leadOver(100, 100, 'Ferrari', false)).toBe('level with Ferrari');
});
