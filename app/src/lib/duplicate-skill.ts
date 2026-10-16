/** Client-side duplicate-name check (FR-012, research R2/R9) -- no LLM
 * call spent on this. Extracted from skills.tsx (002) so dashboard.tsx
 * (004) can reuse the exact same check rather than duplicating it. */

export function normalize(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, ' ');
}

// Small Levenshtein distance -- good enough at "a handful of skills per
// user" scale; no need for a dependency (research R9).
export function levenshtein(a: string, b: string): number {
  const dp: number[][] = Array.from({ length: a.length + 1 }, (_, i) =>
    Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp[a.length][b.length];
}

export function findDuplicate<T extends { name: string }>(name: string, items: T[]): T | undefined {
  const target = normalize(name);
  return items.find((item) => {
    const existing = normalize(item.name);
    return existing === target || levenshtein(existing, target) <= 2;
  });
}
