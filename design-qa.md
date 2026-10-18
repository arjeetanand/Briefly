# Spoken Page design QA

final result: passed

## Visual truth and evidence

- Approved source: `/Users/arjeetanand/.codex/generated_images/01a14da4-c50f-7da3-b508-86097a7cc543/exec-9cdf5fd9-0778-4655-a304-de8068696def.png` (1374 × 1145).
- Implementation: `http://127.0.0.1:8501/`, homepage at scroll position zero, source loaded, motion enabled.
- Desktop CSS viewport: 1374 × 1145. The in-app browser reports devicePixelRatio 0.8 and returns a 1716 × 1431 bitmap with extra right/bottom canvas padding. The comparison removes that padding to retain the actual 1374 × 1145 CSS content; it does not stretch the UI.
- Raw desktop capture: `/private/tmp/pitchroom-design-qa/desktop-final.jpg`.
- Normalized desktop capture: `/private/tmp/pitchroom-design-qa/desktop-normalized.jpg`.
- Full-view source/implementation comparison: `/private/tmp/pitchroom-design-qa/comparison-final.jpg`.
- Focused typography/copy comparison: `/private/tmp/pitchroom-design-qa/detail-final-0.jpg`.
- Focused answer-card comparison: `/private/tmp/pitchroom-design-qa/detail-final-1.jpg`.
- Mobile CSS viewport: 390 × 844. Capture: `/private/tmp/pitchroom-design-qa/mobile-final.jpg`; same padding normalization: `/private/tmp/pitchroom-design-qa/mobile-normalized.jpg`.
- Additional responsive checks: 320 × 800 and 767 × 820. No final horizontal page overflow at the checked widths.
- Scrolling reference: Sweet Tape, https://sweet-tape.com/. Its layered object travel, rotating hero object, oversized type, and overlapping section transition informed the motion, while retaining Pitchroom's approved visual direction.
- Follow-up capture for the scroll/story refinement: `/private/tmp/pitchroom-design-qa/mobile-story-final.png` (390 × 844 CSS viewport; the in-app capture includes padding below the visible web panel).
- Final visible story capture: `/private/tmp/pitchroom-design-qa/phone-story-visible.png` (399 × 870 CSS viewport).
- Final live-room capture: `/private/tmp/pitchroom-design-qa/phone-live-final.png` (399 × 870 CSS viewport).

## Comparison history

1. Initial desktop comparison found P2 drift in type weight and hero spacing, an oversized file-format label inherited from an older selector, and omitted supporting step icons. Updated the display face to DM Serif Display, adjusted hero spacing and image positioning, constrained the label style, and added official Heroicons assets. Compared the revised source and browser capture together in `comparison-final.jpg` and inspected both focused comparisons.
2. Runtime checks found a legacy high-specificity body selector overriding the motion button and skip link positioning. Added equally specific positioning overrides. The motion button now stays in the viewport and the skip link does not reserve flow space.
3. Narrow mobile comparison found P2 overflow at 320px from intrinsic grid sizing, the how-it-works section's double inset, and the live-room header. Removed the extra inset, used minmax(0, 1fr), adjusted the mobile display size, and allowed the stage header to wrap. Rechecked: document scrollWidth equals 320px. Rechecked 390px and captured the final mobile state.
4. Follow-up review found the sticky story changed only text emphasis and left most of its right side empty, while the live room began abruptly. Reworked the story into a layered source → voice prompt → cited answer scene with separate scroll drift, a clearer chapter list, and a stronger live-room introduction/source badge. Mobile keeps a normal stack. Verified all three chapter states in the rendered page and confirmed no horizontal overflow at 390 × 844.

## Required fidelity surfaces

- **Fonts / typography:** DM Serif Display with its true italic preserves the strong editorial headline; DM Sans handles readable UI and body text. Desktop headline retains the approved two-line structure. Mobile deliberately scales the headline to fit narrow screens. No observed truncation of primary copy or controls.
- **Spacing / layout:** Ivory page, asymmetrical two-column hero, open artwork layer, overlaid answer panel, and thin divider preserve the approved hierarchy. The lavender story section now uses a two-column pinned desktop scene with a stacked mobile layout. The live-room heading, current source, and workspace have clearer separation.
- **Colors / tokens:** Ivory `#f8f6ef`, ink plum `#251831`, purple `#7446ba`, and pale lavender replace the former blue visual treatment. Source-connected states retain their semantic labels as well as color.
- **Image quality / assets:** Hero is a generated transparent raster grounded in the selected mockup, rather than a code-drawn substitute. Its ribbon/document proportions and purple/terracotta palette match the visual direction. Step icons are official Heroicons SVG files with their MIT license. The existing product waveform mark is reused.
- **Copy / content:** Approved headline and value proposition retained. The hero answer is labeled as an illustrative example; its footer leads to the actual room rather than pretending to play a prerecorded answer. Typed answers and citations come from the existing backend.

## Function and accessibility checks

- Correct page identity, meaningful content, and no error overlay.
- Browser console checked: no errors or warnings returned.
- Hero demo action produced a grounded answer from the default brief and displayed its source evidence.
- Unsupported valuation question produced the explicit refusal and removed the source peek.
- Sample deck selection loaded `weekly-project-update.pptx`; its sample question produced an answer citing Slide 4. Restored the default brief afterward.
- Native scroll updates hero parallax and moves the source, voice prompt, and cited answer at different rates. Observed Ask, Hear, and Know states with the matching scene layer and progress. Sticky element remained at the 104px header offset during desktop scrolling.
- At 390 × 844 the story becomes a readable normal stack, the live-room source badge fits, and document scrollWidth matches the viewport.
- Follow-up: at 399 × 870 the selected `pitch.txt` and Reset demo fit in a full-width source row; at 1600 × 900 the two-column live-room workspace remains balanced. Browser console reported no warnings or errors.
- Pause/resume tested through the actual UI; paused state stopped the hero animation and showed `aria-pressed=true`.
- Four motion checks pass: pause/resume, system reduced-motion changes, final-chapter/progress clamping, and layered scroll drift/freezing.
- The earlier redesign passed 42 backend tests. This visual follow-up passed the motion checks and JavaScript syntax checks. Scoped `git diff --check` passes; the full-worktree check flags trailing whitespace in `backend/routes/pitch.py`, outside the visual files changed for this follow-up.
- File input stays keyboard reachable; its associated visible upload label receives a focus outline. Skip navigation and visible focus styles are retained.

## Remaining findings / scope

No actionable P0/P1/P2 findings remain in the checked states.

P3: regenerated ribbon line geometry and the freely available display font are close visual matches rather than pixel-identical raster reproductions. Source copy is retained; the illustrative preview footer is intentionally changed to a working navigation action.

Live microphone capture, spoken interruption, real hardware speech quality, other browsers, and a fresh manual file-upload turn were not re-tested in this visual change. No backend or voice logic was changed. Backend tests cover document ingestion.

## Implementation checklist

- [x] Approved homepage style implemented in the existing app.
- [x] Sweet Tape-inspired motion adapted to Pitchroom.
- [x] Actual answer and sample flows verified.
- [x] Desktop, tablet, 390px mobile, pause, and reduced-motion checks completed.
- [x] Source and implementation compared together, then focused regions inspected.
- [x] P2 issues repaired and new captures reviewed.
