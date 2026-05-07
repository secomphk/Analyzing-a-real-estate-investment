# Incident postmortem — `<short title>`

> Copy this file to `docs/postmortems/YYYY-MM-DD-<slug>.md` after an
> incident. Aim to publish within 5 business days.

## Summary

- **Date / window** — `2026-MM-DDTHH:MM:SSZ` → `…`
- **Duration** — `<HH:MM>` (time customer-facing impact was visible)
- **Severity** — SEV1 / SEV2 / SEV3
- **Customer impact** — *one sentence describing what users saw*
- **Root cause (one line)** —

## Timeline

All times in UTC.

| Time   | Event                                           | Who    |
| ------ | ----------------------------------------------- | ------ |
| HH:MM  | First alert: `<monitor name>`                   | system |
| HH:MM  | Acknowledged in `#oncall`                       | <name> |
| HH:MM  | Diagnosis: …                                    | <name> |
| HH:MM  | Mitigation applied: …                           | <name> |
| HH:MM  | All-clear (monitors recovered, smoke test OK)   | <name> |

## Impact

- Users affected: `~N (% of DAU)` or `[component] unreachable`.
- Requests failed / data lost: `…`
- Revenue / SLO consequence: `…`

## What went well

- *(at least one — keeps the doc honest)*

## What went poorly

- *(specific things, not "we didn't catch it fast enough")*

## Root cause

Narrative paragraph. Walk through the chain of events that led from the
contributing cause to the customer-visible failure. Include screenshots
of the relevant graphs / logs.

## Detection

- Monitor that fired (or didn't): `<monitor name>`.
- How long until acknowledged.
- Was this a self-detection or customer-reported?

## Resolution

What ultimately mitigated the impact? Who did it?

## Lessons

Pull-quote-worthy takeaway, in plain language.

## Action items

| ID | Action                                              | Owner | Type        | Due       |
| -- | --------------------------------------------------- | ----- | ----------- | --------- |
| 1  |                                                     |       | prevent     | YYYY-MM-DD |
| 2  |                                                     |       | detect      | YYYY-MM-DD |
| 3  |                                                     |       | mitigate    | YYYY-MM-DD |

Action item types:
- **prevent** — stops the same root cause from happening again.
- **detect** — surfaces the problem faster next time.
- **mitigate** — shortens the impact window.

## Glossary / links

- Linked PRs / commits:
- Linked Grafana dashboards (with the time range pre-filtered):
- Related runbook section: [`runbook.md`](./runbook.md#…)
