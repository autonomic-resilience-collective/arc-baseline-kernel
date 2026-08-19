# Grounding Kernel v2 Architecture

## Boundary decision

ARC's open IHB measurement layer is **neutral evidence infrastructure**.

It answers:

> What is this entity's measured state relative to its own established reference, and how strong/provenant is the evidence supporting that characterization?

It does not decide what a person, clinician, insurer, purchasing agent, habitat controller, ecologist, or other downstream actor should do.

### Layer A — ARC IHB measurement standard

Open/scientific layer:

- observed-data ingestion and de-identification;
- entity-specific baseline construction;
- baseline diagnostics;
- standardized deviation magnitude;
- persistence evidence;
- state/regime evidence;
- missingness provenance;
- source/device epochs;
- source-comparability evidence;
- deterministic fingerprints/provenance.

This layer must remain usable across physiology, ecology, habitat systems, assays, and other longitudinal domains without embedding a domain action policy.

### Layer B — domain interpretation adapter

A domain profile supplies scientifically justified parameters and meaning:

- baseline duration and minimum observations;
- sampling cadence;
- persistence criteria;
- segmentation rules;
- change-point algorithm/thresholds;
- source-comparability criteria;
- interpretation of positive/negative deviation in that domain.

ARC may publish open research adapters where appropriate. Domain experts own the scientific justification for these profiles.

### Layer C — commercial/operational decision policy

Commercial or operational software may consume Layer A + validated Layer B outputs and decide what action to take. Examples include purchasing, workflow routing, coaching, underwriting research, habitat response, or other enterprise behavior.

Where proprietary implementation is appropriate, this is the natural Autonomic Dynamics boundary. The open IHB measurement standard should not be modified merely to create a commercial recommendation.

## Compatibility strategy

The existing v1 service remains intact during migration so current routes/payment work are not broken.

v2 introduces new neutral routes under `/v2/*`. Once v2 scientific validation and client migration are complete, legacy action strings in `ihb_categories.yaml` can be deprecated or moved into a downstream adapter rather than deleted abruptly.

## Source integrity

The canonical mathematical source is the private `ARC-IHB-Engine` repository. The Grounding Kernel vendors that package for deployment and records upstream provenance in `ihb/UPSTREAM.md`.

A missing canonical package is a deployment failure. Production must not silently substitute fallback math.

## Validation gates before calling v2 production-validated

- test suite passes against canonical core;
- persistence/change-point behavior benchmarked under known synthetic/semi-synthetic transitions;
- prospective replay distinguished from retrospective segmentation;
- baseline diagnostics benchmarked under autocorrelation/skew/heteroscedasticity;
- source epoch transitions cannot create false biological/ecological regimes;
- source pooling remains unauthorized absent explicit domain comparability criteria;
- v2 result schema receives scientific review;
- documentation matches deployed behavior.
