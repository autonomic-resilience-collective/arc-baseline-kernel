# Vendored IHB math provenance

The Grounding Kernel's `ihb/` package is sourced from the private canonical repository:

`autonomic-resilience-collective/ARC-IHB-Engine`

Canonical core file at the time this vNext hardening branch was created:

- upstream path: `ihb/core.py`
- upstream blob SHA: `eccd4a3028144702b53bf2096602591c3075f5df`
- upstream branch observed: `main`

The vNext methodological primitives were developed in parallel on branch `ihb-vnext-methods-hardening` in the upstream engine repository.

## Integrity rule

Production Grounding Kernel deployments must use the canonical ARC IHB math package. A missing package is a deployment failure, not permission to silently substitute an alternate implementation. Any future vendoring update should record the upstream commit/blob provenance here and pass parity tests before release.
