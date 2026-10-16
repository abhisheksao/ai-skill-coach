import type { DashboardResponse } from './api';
import { readCachedDashboard, writeCachedDashboard } from './dashboard-cache';

// AsyncStorage's native module isn't available under plain jest-expo --
// use the library's own official jest mock, scoped to this file only (no
// shared jest config change needed for one pure-logic test file). Must
// use require() here: jest's mock-factory hoisting forbids referencing
// an imported binding from outside the factory.
jest.mock('@react-native-async-storage/async-storage', () =>
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

const SAMPLE: DashboardResponse = {
  skills: [
    {
      skill_id: 'skill-1',
      name: 'Swimming',
      goal_statement: 'Swim 1km',
      target_date: '2026-12-01',
      is_stale: false,
      progress: { completed_steps: 1, total_steps: 3, streak_days: 2 },
      steps: [
        { order: 1, description: 'Float and glide', completed: true, behind_cadence: false },
      ],
    },
  ],
};

describe('dashboard-cache', () => {
  it('returns null when nothing has been cached yet', async () => {
    expect(await readCachedDashboard()).toBeNull();
  });

  it('round-trips a written dashboard response', async () => {
    await writeCachedDashboard(SAMPLE);
    expect(await readCachedDashboard()).toEqual(SAMPLE);
  });

  it('a later write overwrites the earlier cached value', async () => {
    await writeCachedDashboard(SAMPLE);
    const updated: DashboardResponse = { skills: [] };
    await writeCachedDashboard(updated);
    expect(await readCachedDashboard()).toEqual(updated);
  });
});
