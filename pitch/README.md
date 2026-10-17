# Pitch package

| File | What it is |
|---|---|
| `ScopeGuard_Pitch.pptx` | Editable 8-slide 16:9 deck (13.333 × 7.5 in). Native text, shapes, connectors and an editable chart; speaker notes on every slide. |
| `ScopeGuard_Pitch.pdf` | PDF exported by PowerPoint during rendering |
| `PITCH_SCRIPT.md` | Timed 3:40 script, demo click path, fallbacks, judge Q&A, optional Georgian lines |
| `build_deck.js` | PptxGenJS generator. It reads `docs/demo_results.json` (and the live run, if present) and **fails** if evidence is missing, failed or unsafe. |
| `lib/apply_theme.js` | Writes the theme colors and fonts into the PPTX. Vendored from the Claude `pptx` skill. |
| `make_icons.mjs` | Renders Lucide icons (ISC license) to PNG through Playwright |
| `assets/` | Real UI screenshots (`demo-*.png`, live mode), icon PNGs, `evidence.json` snapshot |
| `render_deck.ps1` / `render_deck.vbs` | PowerPoint COM renderer: slide PNGs, PDF, and `qa/layout-report.json` (bounds and text-overflow check) |
| `make_montage.py` | `qa/montage.png` contact sheet |
| `check_deck.py` | Structural and provenance checks (see below) |
| `qa/` | Renders, montage, layout report and `review.json` (visual review bound to the PPTX SHA-256) |

`check_deck.py` verifies:

- 8 slides and 8 notes pages
- 16:9 page size
- native chart data
- the required text is present
- no secrets or personal data appear
- the evidence snapshot matches the current results
- the renders exist
- the review hash matches the current deck

## Regenerate (from the repo root)

```powershell
.\.venv\Scripts\python.exe -m scripts.run_demo_scenarios --mode deterministic --reset --output docs/demo_results.json
.\.venv\Scripts\python.exe -m scripts.run_demo_scenarios --mode live --output docs/demo_results_live.json   # optional, needs a key
# optional: refresh the UI screenshots used on slide 6 (with run_local running on :8000)
node scripts/capture_demo.mjs --out docs/screenshots/live --assets
node pitch/make_icons.mjs                    # only if icons are missing
npm run pitch:build
powershell -NoProfile -ExecutionPolicy Bypass -File pitch/render_deck.ps1
.\.venv\Scripts\python.exe pitch/make_montage.py
.\.venv\Scripts\python.exe pitch/check_deck.py
```

Rebuilding changes the PPTX hash, so `check_deck.py` will fail until each slide is visually re-reviewed and `qa/review.json` is updated. That is deliberate: a structural check does not replace looking at the slides.

## Rendering note

On the build machine, PowerPoint's typed PowerShell interop fails (`TYPE_E_ELEMENTNOTFOUND`). The renderer therefore uses late-bound IDispatch through VBScript. It:

- opens the deck read-only and without a window,
- closes only its own presentation,
- quits PowerPoint only if it had no other presentations open.
