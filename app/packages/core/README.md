# @abhisheksao/ai-skill-coach-core

Reusable Expo building blocks for AI coaching apps, extracted from
[ai-skill-coach](https://github.com/abhisheksao/ai-skill-coach):

| Import | What it gives you |
|---|---|
| `/supabase` | `createSupabaseClient(url, anonKey)` with session storage that works on native and web |
| `/oauth` | `createOAuth(supabase, { scheme })`: Google (and Apple) sign-in |
| `/api-client` | `createApiClient(supabase, apiUrl)`: fetch wrapper that attaches the Supabase JWT |
| `/use-voice-session`, `/voice-capabilities` | Push-to-talk speech recognition and text-to-speech |
| `/theme` | Design tokens |
| `/components/*` | `screen`, `primary-button`, `text-field`, `loading-dots`, `chat-bubble` |

The package never reads env vars: pass configuration in.

It ships TypeScript source and is meant for Expo/Metro apps. If you run
Jest, add `@abhisheksao` to `transformIgnorePatterns` so the package gets
transformed.

## Install (GitHub Packages)

```bash
# .npmrc
@abhisheksao:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}   # a token with read:packages
```

```bash
npm install @abhisheksao/ai-skill-coach-core
```

Peer dependencies (Expo SDK modules, `@supabase/supabase-js`, `react-i18next`)
are listed in `package.json`.

Apache-2.0.
