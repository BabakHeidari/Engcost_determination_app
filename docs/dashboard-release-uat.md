# PR-10 manual owner UAT

**Owner sign-off: PENDING.** Automated fixture evidence is technical validation,
not owner acceptance or production approval. Record reviewer, canonical factory,
installed period, exact configuration identities, code SHA, date and outcomes.
Use approved current inputs; screenshots committed by PR-10 use synthetic fixtures.

| Check | Expected behavior | Owner result |
|---|---|---|
| Admission and cascade | Authorized active factory only; category/subcategory/composite references preserve at least two distinct configurations | PENDING |
| Cost Analysis ALL | Explicit ALL expands only selected scope; exact period dates display Jalali; full-category denominator is independent of local focus | PENDING |
| Complete and incomplete records | Inspect two exact configurations and one incomplete record; PARTIAL, calculated/excluded counts and reasons remain visible; unavailable is not zero | PENDING |
| KPI and exact values | Unit IRR/product, projected IRR/period, weighted numerator/denominator, top driver/ties and visible reconciliation match source-approved calculations | PENDING |
| Cost exploration | Composition, stacked products, hierarchy, material Pareto, product/factor heatmap and scatter use documented units; drill/focus preserves KPI and full CSV | PENDING |
| Parameter permissions | Dashboard-only has derived results; general READ and same-factory factory READ separately expose controls; MODIFY is unnecessary; revoked/wrong-factory grants fail safely | PENDING |
| Independent A/B | Enter distinct drafts; baseline/A/B use one fresh capture; verify A−baseline, B−baseline and B−A directions and reference denominators | PENDING |
| Waterfalls | Seven output differences and technical reconciliation explain unit delta; no independent causal attribution is claimed | PENDING |
| Experiments | Tornado supplied ranges, actual one-factor samples and two-factor cells; invalid points remain unavailable, never silently clipped/zero | PENDING |
| Freshness and Reset | Draft/range/selection edits invalidate previous results/CSV; refresh reads current sources; Reset clears A/B/experiments and keeps authorized baseline | PENDING |
| Exact/copy and CSV | Keyboard and touch exact inspection/copy; original Decimal strings, identities, directions, UTF-8 BOM, quoting and no formula execution | PENDING |
| Tablet/mobile | Readable RTL at desktop/tablet/narrow mobile; large tables scroll within their containers; primary controls remain operable | PENDING |
| Failure fallback | Chart library failure retains exact tables/CSV; expired login, denied permission, unavailable inputs, schema/network errors clear or retain context per contract | PENDING |
| Persistence and scope | Dashboard requests make no source/config/profile/scenario writes after prepared startup; data is current/hypothetical, with no historical cost trend | PENDING |

Any unresolved P0/P1 affecting security, costing, permissions, persistence or the
default journey blocks release. Document the defect and repeat its check after
resolution. Approval requires explicit owner sign-off; no automated result marks
this table accepted.
