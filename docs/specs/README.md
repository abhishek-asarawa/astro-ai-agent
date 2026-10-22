# Feature specs

Curated product definitions for what the agent should deliver to users.

These are **business** specs: purpose, inputs, required answer content, classical grounding, and success signals. They are not implementation plans.

Product direction and the order in which themes get built live in [docs/ROADMAP.md](../ROADMAP.md); roadmap steps link to the spec they implement. Engineering backlog and deferred engineering work stay in [docs/FUTURE_IMPROVEMENTS.md](../FUTURE_IMPROVEMENTS.md). Specs here are the product contract when a theme is prioritized.

## Status legend

| Status | Meaning |
|--------|---------|
| **live** | Supported for users today (within current corpus / chart pipeline) |
| **planned** | Defined product intent; not yet grounded or shipped |
| **deferred** | Intentionally postponed (see backlog); no active product contract yet |

## Index

| Spec | Status | Notes |
|------|--------|--------|
| [career-guidance.md](career-guidance.md) | live | Profession / work questions via career intent |
| [timing-windows.md](timing-windows.md) | live | Date horizons, dasha transitions, countdowns |
| [manglik-detection.md](manglik-detection.md) | planned | Mangal / Kuja dosha for marriage context |
| [sade-sati.md](sade-sati.md) | planned | Saturn Sade Sati / Dhaiya periods |
| [guna-milan-matching.md](guna-milan-matching.md) | planned | Ashtakoot / Guna Milan compatibility |
| [remedies.md](remedies.md) | planned | Gemstones, puja, mantra, charity (cross-cutting) |

## How to use

1. Before changing user-facing behavior for a theme, open the matching spec.
2. When promoting a backlog theme to product work, write or update a spec here first; keep `FUTURE_IMPROVEMENTS.md` as the engineering backlog.
3. Mark status **live** only when grounding and success signals are actually met in product.
