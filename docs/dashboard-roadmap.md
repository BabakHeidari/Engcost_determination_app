# Dashboard roadmap

PR-05–PR-09 provide the approved shared engine, current Cost Analysis report,
Persian presentation, authorized parameter registry and non-persistent scenarios.

PR-09A completes current-data visual exploration and the shared-input A/B lab,
Tornado, actual one-factor responses and bounded two-factor experiments before
PR-10 hardening. See [API and semantics](pr09a-dashboard-visual-analytics.md) and
[Persian user guide](dashboard-visual-analytics-user-guide.md).

PR-10 hardens existing request limits, typed errors, response validation and
request-local engine work, and supplies isolated regression/browser evidence,
repeatable benchmarks, pinned dependencies and an operational handover. See
[release readiness](pr10-dashboard-release-readiness.md) and the
[manual UAT checklist](dashboard-release-uat.md). Technical checks and owner UAT
are separate; owner sign-off remains PENDING. No deployment or production release
approval is included. PR-11 is not started.

No source editing, persisted scenarios, history cache, sharing, optimization or
forecasting is introduced by these Dashboard changes.

Historical cost-series analysis requires a separately approved future feature
for authoritative historical capture, retention, permissions and provenance.
The owner currently has only operational data; current inputs, planning periods,
fingerprints and owner-assigned legacy baselines must not be relabeled as a cost
history or silently saved to manufacture one.
