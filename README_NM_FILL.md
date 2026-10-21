# NM mock filler (first iteration)

This package adds **NM-specific files only**. CA remains unchanged. The mock must have at least two unit tabs.

1. Extract ZIP into your KeyForMe project root on `feature/nm-support`.
2. Run `python -m compileall -q app tests`.
3. Run `python -m tests.test_nm_fill` to fill **fake values** into the first two NM mock units.
4. Inspect Unit 1 and Unit 2. Report any `Warnings:` lines and incorrect fields.

**Safety gates:** Does not Save/Submit; does not register NM in `PIPELINES`; does not click the VIN confirmation popup; does not guess dropdown options. It does not attempt to add units in a static mock. Live NM support remains disabled until selectors and dropdowns are validated.

The Codegen recording confirms many IDs, but the actual captured NM HTML has not been supplied here. Selector correctness against your local mock therefore still needs your test.
