/** Offline stale-data fallback for the home dashboard (004, research.md
 * R10) -- the last successful GET /v1/dashboard response, cached so a
 * failed refetch (e.g. no network) can still render something instead of
 * an empty/error screen, with a "stale data" indicator. Never treated as
 * authoritative -- overwritten by the next successful fetch. Same
 * established pattern as 001's read-failure handling, just for this one
 * screen (quickstart scenario 22).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { DashboardResponse } from './api';

const CACHE_KEY = 'skillcoach.dashboard-cache.v1';

export async function readCachedDashboard(): Promise<DashboardResponse | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as DashboardResponse) : null;
  } catch {
    return null;
  }
}

export async function writeCachedDashboard(dashboard: DashboardResponse): Promise<void> {
  try {
    await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(dashboard));
  } catch {
    // Best-effort cache -- a write failure just means no offline fallback
    // next time, not a user-visible error now.
  }
}
