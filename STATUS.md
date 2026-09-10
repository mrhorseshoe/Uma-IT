# Status

Where the build has got to. See `DESIGN.md` for why the project is shaped this
way, and for the rules any new handler has to respect.

## Done

- [x] Repository, layout and design recorded
- [x] Engine vendored unchanged — `bot/`, 3,566 lines, 35 files
- [x] Calibrated assets moved verbatim and verified
      — 28 template PNGs, 28 template declarations, 22 screens, 38 click points
      — `check_assets.py`: all resolve, all decode, no screen references a
        template outside the package
- [x] Dialog title scoring set extracted — 23 owned, 36 distractors, 59 total
      — `check_titles.py`: every owned title wins its own frame, no distractor
        is wrongly taken, and `'Final Confirmation'` resolves to itself

## Next

- [ ] `uma_it/context.py` and `uma_it/task.py` — 20 fields, not 50, and every
      one of them restart-durable
- [ ] `uma_it/manifest.py` — app registration and the screen -> handler table
- [ ] `uma_it/career.py` — the countdown handler; clicks nothing (rule 3)
- [ ] `uma_it/dialogs.py` — the title router, matching at 0.8 only
- [ ] `uma_it/start.py` — career start, career-mode failsafe, pending-run
      rescue. **The one part never run against the live game** (see DESIGN.md)
- [ ] `uma_it/agenda.py` — the slot-1 picker; read the scrollbar (rule 2)
- [ ] Enter and collect handlers — ~300 lines
- [ ] `main.py` — device checks, scheduler, HTTP server
- [ ] Web UI — IT-only; the parent project's task modal is 5,330 lines for a
      career mode this app does not play
- [ ] Optional: skill buying (~450 lines), spark reroll (~180)

## Line budget

Target is ~2,050 lines for the core and ~2,700 with both optional features,
against the parent project's 9,415 lines of module Python.

| Piece | Estimate |
|---|---|
| Assets (done) | ~200 |
| Enter/collect handlers | ~300 |
| Blind fallback, IT-only | ~60 |
| Parse helpers, core | ~180 |
| Task + context | ~150 |
| Hooks | ~120 |
| Router, start, agenda, career, manifest | ~1,040 |

## Checks

```bash
py -3.10 check_assets.py
```

```bash
py -3.10 check_titles.py
```

Both exit non-zero on failure. Run them after touching anything under
`uma_it/asset/`.
