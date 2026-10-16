# Release Runbook

Local-build distribution to TestFlight (iOS) and Play internal testing
(Android) — no EAS Build/CI (001's FR-008 decision stands; this is about
linking Expo's push-token *service* identity only, unrelated). Executed
once per platform before the first pilot invite (research.md R11).

## Prerequisites

- Apple Developer Program membership (~$99/yr, human-executed, T060) and
  a Play Console account ($25 one-time, T060).
- Xcode (iOS) / Android Studio + a JDK (Android) installed locally.
- `app/app.json`'s `extra.eas.projectId` already links this app to its
  Expo project (004) — needed for push tokens, not for this build path.

## iOS — TestFlight

1. `cd app && npx expo prebuild --platform ios --clean` (regenerates the
   native `ios/` project from `app.json`/plugins — do this after any
   config change, e.g. a new plugin).
2. Open `ios/SkillCoach.xcworkspace` in Xcode.
3. Set the signing team to the Apple Developer Program account; confirm
   the bundle identifier matches what's registered in App Store Connect.
4. **Product → Archive.** Once archived, **Distribute App → App Store
   Connect → Upload.**
5. In App Store Connect → TestFlight, wait for processing, then add the
   build to an internal testing group (no App Review needed for internal
   testers).
6. Invite the pilot cohort's iOS testers by email; they install via the
   TestFlight app.
7. **Versioning**: bump `app.json`'s `expo.version` (marketing version)
   and let Xcode auto-increment the build number each archive, or set
   `ios.buildNumber` explicitly in `app.json` before prebuild.

## Android — Play internal track

1. `cd app && npx expo prebuild --platform android --clean`.
2. Generate (once) or reuse an upload keystore; configure signing in
   `android/app/build.gradle` (or `gradle.properties` for
   the keystore path/credentials — never commit these).
3. `cd android && ./gradlew bundleRelease` — produces
   `app/build/outputs/bundle/release/app-release.aab`.
4. Play Console → your app → **Testing → Internal testing → Create new
   release** → upload the `.aab` → roll out.
5. Add pilot testers by email to the internal testing list; share the
   generated opt-in URL — they install via the Play Store once opted in.
6. **Versioning**: bump `app.json`'s `android.versionCode` before each
   `prebuild` (Play requires a strictly increasing integer per upload).

## Execution log

| Date | Platform | Build/version | Outcome |
|------|----------|----------------|---------|
| _(pending — human-executed, T061)_ | | | |
