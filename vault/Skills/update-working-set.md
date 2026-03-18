---
type: skill
status: active
category: state
trigger: update_working_set
description: Update the canonical active working set so every agent reloads the same mission, priorities, and next actions
source: Command Center MCP
targets: [claude, codex, openclaw, openfang, any-ai]
---

# update_working_set

Writes the active working set to `Core/ACTIVE_CONTEXT.md`.

Use it after:
- major strategy changes
- production incidents
- priority shifts
- any point where a future session must resume from the same state

## Usage
```text
update_working_set(
  project="my-app",
  mission="Ship the v1 checkout flow without regressions",
  summary="Cart and payment screens done, confirmation screen pending",
  priorities=["Wire Stripe webhook", "Add order confirmation email"],
  next_actions=["Resume from PaymentIntent callback handler"]
)
```
