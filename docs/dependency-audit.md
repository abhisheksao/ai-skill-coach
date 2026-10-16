# Dependency audit (app/)

`npm audit` in `app/` reports advisories that come almost entirely from
Expo / React Native / Jest build tooling. This file records the triage so
the remaining report is a known, reviewed list rather than noise.

**Last triaged:** 2026-10-13 (Expo SDK 57, react-native 0.86.3, lockfile
committed). **Result:** 77 reported → 65 reported (0 critical). The 65 are
dependency chains of just **5 root advisories**, none of which has a
non-breaking fix; all are accepted below.

## What was fixed

- `npm audit fix` (in-range bumps only): shell-quote (critical), node-forge
  holders, xmldom, js-yaml, brace-expansion, browserslist, fast-uri, nanoid,
  postcss, source-map-js, image-size, among others.
- Expo SDK 57 packages aligned to `npx expo install --check` (the in-range
  `expo` bump to 57.0.28 left the exact-pinned SDK modules behind;
  react-native 0.86.0 → 0.86.3, jest-expo → ~57.0.6).
- `overrides.compression = 1.8.2` (GHSA-vc2v-76pw-4v95): `serve` exact-pins
  1.8.1; 1.8.2 is a patch release.

## Accepted (no non-breaking fix)

`npm audit fix --force` would "fix" these by downgrading to Expo SDK 44 /
react-native 0.72 or jumping majors — never run it.

| Advisory | Package (path) | Ships in app? | Why accepted |
|---|---|---|---|
| [GHSA-vcc3-ghjq-m6fr](https://github.com/advisories/GHSA-vcc3-ghjq-m6fr) (moderate) | decode-uri-component 0.2.2 (expo-router → query-string 7) | **Yes** (URL parsing) | Worst case: a crafted link freezes the tab/app of the user who opens it. No data exposure, no server-side use. The patched 0.4+/0.5 is ESM-only and breaks query-string 7's `require()`. Fix arrives with expo-router SDK 58 — **revisit on the SDK 58 upgrade**. |
| [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) (high) | node-forge (expo → @expo/cli, @expo/code-signing-certificates) | No | Build/dev CLI only; used for expo-updates code signing, and expo-updates isn't installed. No patched version. |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) (high) | braces (micromatch ← jest, metro) | No | Dev/build file matching over our own glob patterns. No patched version. |
| [GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) (moderate) | sprintf-js (argparse ← js-yaml 3 ← istanbul) | No | Jest coverage tooling only. No patched version. |
| [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq) (moderate) | uuid 7 (xcode ← @expo/config-plugins) | No | Prebuild tooling; the bug needs v3/v5/v6 with a caller buffer, and xcode only calls `uuid.v4()`. |

## Re-checking

```bash
cd app
npm audit                    # expect only the 5 roots above
npx expo install --check     # SDK modules must match the installed expo
```

A new root advisory (not in the table) needs a triage entry here or a fix.
The lockfile is committed; because the maintainer's global gitignore
excludes lockfiles, stage updates with `git add -f app/package-lock.json`.
