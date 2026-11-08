# Spider-Man 2 support

User approved the native-resource integration route from the feasibility report: add Spider-Man 2 to the existing Windows subtitle tool, using large English above small Chinese by default preset, while preserving Miles and all existing configurable styles/layouts and restore functionality.

## Approach
Use a separate I29 archive adapter plus native HTML/JS subtitle adapter. Reuse Profile, pairing, short MMID transport and safe reversible installer. Alternatives (external overlays or forcing the old GFX route) do not meet the requested native integrated tool. No game-specific restriction is relaxed for Miles.

## Scope
- Recognize Spider-Man2.exe + root toc + d/, resource baseline 2.810.0.0; unknown modifications rejected.
- Independent language span table (English0, simplified168, traditional176); discover other available languages from actual resources before enabling them. English audio/timing retained, Chinese menus unchanged.
- Read/write direct localization DAT1, I29 TOC, local generated resource archive. No original bulk game archive overwrite.
- Patch overlay.js in player's own game: keep two native subtitle slots and lifecycle, render independent upper/lower text with measured wrapping, stacked or split configuration, single layers, styles and output-pixel margins.
- GUI chooses/discovers game from directory, shows correct version, launch executable, process guard, resolution and language support. v1/v2 profile compatibility retained.
- Validate a short native sample first, then 29,609 dialogue entries. Backup latest game-specific saves before any gameplay test and restore only test changes. Never operate on user gameplay concurrently.
- Portable Windows update, example profile, usage/compatibility report, public source/release after verification. Do not ship game texts/resources/saves.

## Evidence requirements
Archive bounds, payloads/index backup hashes, interruption/restore and process guards; functional DOM tests for two slots/hide/long lines/missing layers; generated resource readback; native real-game rendering confirmation; portable runtime + ZIP/manifest checks; Miles regressions. Tests or compilation alone do not prove game rendering.
