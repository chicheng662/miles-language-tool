# Stacked Subtitles Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Ship adjustable adjacent large-English/small-Chinese native subtitles.
**Architecture:** Retain the dual native fields; add schema migration, measured stacked groups, and matching GUI preview.
**Tech Stack:** Python/Tkinter, ActionScript 3, JPEXS, PyInstaller.
**Spec:** docs/superpowers/specs/2026-10-31-stacked-subtitles-design.md

## Global Constraints
- Preserve old split settings and per-language font choices; v1 imports as split.
- Default preset 36/24, bottom margin 100 output px and gap 8 output px.
- Use only supported game resources locally; never publish them or saves.
- Existing restore/backups and game process guards remain active.

## Review Focus
- Old schema input must preserve the former layout and reject malformed versions.
- Wrapped upper/lower text and absent translations must not leave overlapping or empty groups.
- Both subtitle slots must reserve whole bilingual group height, including when one hides.
- Non-dialogue native text, fades and single-layer settings must preserve native ownership.
- Changing resolution or switching layout must not silently discard settings or confuse preview.

### Task 1: Configuration and layout geometry
Files: configuration.py, subtitle_layout.py, tests/test_configurator.py, tests/test_subtitle_layout.py.
Interfaces: Profile.english_first(), Profile.bottom_ui_y(), stacked_pairs(bottom_edge, heights, line_gap, speaker_gap).
- [x] Add migration/default/preset validation tests and wrapped/single/double-group geometry cases; run and observe RED.
- [x] Implement schema 2 and measured-pair positioning; run base suite GREEN.
- [x] Commit configuration and tests.

### Task 2: Native component and tool controls
Files: configurable_overlay.py, configurator_app.py, tests/test_configurator_backend.py, tests/test_configurator_gui.py.
- [x] Add real-source tests for stacked generation, legacy split, slot lifecycle and font styles; observe RED.
- [x] Add stacked positioning based on TextField.getBounds and active subtitle flags; preserve parenting and independent styles.
- [x] Add layout selector, English-first action, bottom margin/gap controls, and measured preview; check them using Tk without applying a patch.
- [x] Compile/read back short, wrapped and single-layer profiles using the local original overlay. Run supported local tests GREEN and commit.

### Task 3: Portable update and publication
Files: package_tool.py, README.md, 工具使用说明.md, 验证报告.md.
- [x] Bump preview to v0.2.0; include subtitle_layout.py and English-first example. Preserve all licenses.
- [x] Build separate updated portable folder; run isolated runtime self-test and ZIP CRC/SHA/asset-exclusion checks.
- [x] Perform a fresh branch review and resolve important findings with reproductions.
- [x] Fast-forward main after checks, publish prerelease assets and verify server digests and CI. Update the user's local launcher without overwriting the old package.
