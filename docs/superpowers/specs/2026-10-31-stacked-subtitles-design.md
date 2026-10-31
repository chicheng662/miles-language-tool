# Bottom stacked bilingual subtitles

## Intent and accepted layout
The user requested and confirmed large English above small Chinese, adjacent in the lower subtitle area. The old split layout remains available. Update the portable tool and the public GitHub preview.

## Approach
Selected: a new native stacked layout using the existing two independently styled layers, with measured text bounds and per-speaker groups. Raising the old top-offset limit alone cannot keep wrapped lines adjacent. Merging languages in one native text field would weaken independent typography and single-layer controls.

## Behavior
- Add schema v2: layout `split` or `stacked`, bottom_margin_px=100 and line_gap_px=8. These two distances are output pixels. Keep v1 import as the original split layout; existing preferences and installed patches remain readable.
- One-click English-first preset: stacked, top_language=en/top_size=36, bottom_language=zh-CN/bottom_size=24. These sizes are implementation defaults, adjustable by the user. Preserve resolution and other styles.
- Upper/lower refer to the order within the group in stacked mode. Wrap using native text fields; position upper immediately above lower using measured bounds. Stack the second speaker's whole bilingual group above the first. Single layers and missing upper translations consume no empty gap.
- Keep layers attached to the owning native subtitle MovieClip, preserving fades, hiding, pause and load lifecycle. Reflow active groups when a subtitle is shown or hidden.
- Preview uses measured wrapped text height. Add layout choice, preset and bottom/gap controls; split-mode top offset retains its resolution-aware validation.

## Constraints and acceptance
Windows portable folder; supported game resource version unchanged. No game resources or player saves in GitHub. Automated migration/geometry tests, real native compilation and readback, GUI checks, packaged runtime checks, archive checks and GitHub CI. Game appearance must be distinguished from compile/preview evidence. Do not load or overwrite player progress for this update without a current backup and authorization.
