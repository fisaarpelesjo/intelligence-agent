# `daily_reporting` — the daily KPI report and the rule alert

Feature `008`. See `specs/008-daily-report-and-rule-alerts/`.

## Two products, and they must never merge

| | the daily report | the alert |
|---|---|---|
| what it carries | **all twenty KPIs**, every day | one KPI, when it moves |
| threshold | **none** | that KPI's own `p90` |
| when it speaks | every day, unconditionally | only on a crossing |

The owner separated them himself after the first question mixed them. **A summary that
silently drops a KPI is a claim nobody made, and an alert that fires on everything is a
summary wearing an alarm.** They have separate entry points here, and a node asserts
neither calls the other.

## What this package does NOT do

**It sends nothing.** No transport, no channel, no readiness record written. Origination
is governed by `ADR 0036` and lives in Phase E, which is held for review.

**It writes no KPI name and no section header.** Both are derived from the view's own
`kpi_name` and `section_name`, and a node fails when a derivation is replaced by a
**correct** literal.

**It writes no `p90`.** The threshold is computed from the series at run time. A `p90`
table in source is the `F136` failure — correct today, drifting away from the data every
day after.

**It converts no currency.** The view keeps the two currencies in separate columns and
holds no exchange rate, so a converted figure would depend on a rate the reader chooses.

**It originates nothing outside a called run.** No scheduler, no timer, no thread, no
event loop, and no console script.
