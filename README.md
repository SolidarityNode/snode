# SolidarityNode

**Open-source spatial probabilistic framework for social service accessibility, latent need, vulnerability and resilience.**

> **Status: early-stage research software.** SolidarityNode is under active design and development. APIs, data models and methods will change. Nothing here is validated for operational decision-making yet.

---

## What is SolidarityNode?

SolidarityNode is an open-source platform that moves the analysis of social infrastructure (healthcare facilities, social care and other public services) from a static map of spatial adequacy to a **dynamic, probabilistic view**.

It combines in a single framework:

- spatial **accessibility** and **capacity** of service facilities,
- estimation of **latent (unobserved) social need**,
- **social vulnerability** of different population groups to loss or degradation of a service,
- **real operational data** from the services themselves,
- the **dynamics of impact and recovery** over time, leading to estimates of system **resilience**.

A degraded facility is not automatically treated as lost service. The platform estimates what the population of each area actually loses, given the alternative facilities and routes available in the network, and how the system recovers after a disruption.

## Core ideas

**Unit of analysis.** Everything is modelled at the level of:

> spatial unit × social group × service × time

**Vulnerability is not resilience.** Vulnerability expresses a baseline predisposition to adverse effects, given exposure, service loss and social susceptibility. Resilience is a dynamic property that emerges from the trajectory of loss and recovery. They are modelled separately.

**Facility state is not population-level service loss.** A facility can be degraded without any loss of coverage for the population, if other facilities or routes can absorb the demand. Analysis therefore moves from the individual facility to the service network.

**Observed demand is not need.** Recorded demand is only part of the total need. Barriers to access, socioeconomic factors and limited awareness create hidden need, which the framework estimates explicitly.

**Uncertainty is first-class.** Methods are probabilistic (Bayesian Networks, Dynamic Bayesian Networks and other suitable spatial or probabilistic methods) so that results carry uncertainty instead of single deterministic numbers. Prior estimates are updated as real operational observations accumulate.

## Planned capabilities

Modules of the `core` library, following the module map in [`docs/specs/00-domain-model.md`](docs/specs/00-domain-model.md) §6:

| Module | Papers | Purpose |
| --- | --- | --- |
| `model` | all | Entities and the typed container for `spatial unit × social group × service × time` |
| `bayes` | 1–4 | Discrete variables, CPTs, expert elicitation, inference and parameter-learning interfaces |
| `accessibility` | 1 §5 | Travel times, access weights, group- and mode-specific accessibility |
| `demand` | 1 §6 | Estimated demand (visible use, not need) |
| `capacity` | 1 §7 | Physical, functional and effective capacity, supply (2SFCA allocation) |
| `service_gap` | 1 §8–9 | Service gap and its Bayesian network |
| `latent_need` | 2 | Social susceptibility, hidden need, estimated total need |
| `scenarios` | 1 §13, 3 §7–10 | Counterfactual and disruption scenarios |
| `vulnerability` | 3 §11–21 | Group exposure, service loss, the vulnerability relationship |
| `operations` | 4 §4–5 | Anonymous request tickets, operational indicators, facility functional state |
| `dynamics` | 4 §7–9, 12 | Territorial state, expected and observed consequence, Dynamic Bayesian Network |
| `resilience` | 4 §10–13 | Bayesian updating of vulnerability, recovery trajectories, resilience |
| `uncertainty` | 1 §11, 2 §14, 3 §22 | Monte Carlo propagation |
| `sensitivity` | 1 §12, 2 §16, 3 §23 | Sensitivity analysis |
| `validation` | 1 §14, 2 §18, 3 §24 | Validation tools |

At this stage the modules expose typed interfaces only; methods are implemented once their open questions are decided (see [`docs/specs/open-questions.md`](docs/specs/open-questions.md)).

A **Digital Twin** is a possible long-term direction, not a starting assumption. The architecture aims not to rule it out, while the framework first investigates whether a probabilistic, dynamic model can serve as its foundation.

## Planned architecture

```
solidaritynode/
├── core/        # simulation and modelling library (Python), no web or database dependencies
├── backend/     # API, scenario and run management, anonymous request-logging mechanism
├── frontend/    # web interface: maps, scenarios, results
├── docs/        # architecture, specifications, decision records
└── .github/     # CI, issue and PR templates
```

Dependency direction: `backend` depends on `core`; `core` never imports from `backend` or `frontend`. This keeps the modelling library testable and reusable on its own.

## Data and privacy

Social service data can be sensitive.

- **No real personal or operational data is ever committed to this repository.** Only synthetic data is used for tests and demos.
- The operational data mechanism is designed to be **anonymous** (for example QR codes or an appointment system) and to record only what is needed: spatial origin of the request, social group, service type and timestamps.
- Deployments are responsible for complying with applicable data protection law (for example the GDPR in the EU).

## Getting started

Requirements: `git`, `make`, [`uv`](https://docs.astral.sh/uv/), Node.js 26 with `pnpm` 12, and Podman (default) or Docker.

```bash
make setup        # install dependencies
make lint test    # lint, type check and test everything
make up           # start database, backend and frontend (Podman by default)
```

Then open http://localhost:8080. With Docker: `CONTAINER_ENGINE=docker COMPOSE="docker compose" make up`. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md).

## Roadmap

- [ ] **v0.1**: `core` with a minimal model on synthetic data; `docs/architecture.md`
- [ ] **v0.2**: accessibility and capacity module, backend API
- [ ] **v0.3**: latent need and vulnerability models, first frontend
- [ ] **v0.4**: operational data ingestion, dynamics and resilience indicators
- [ ] **v0.5**: validation tools, sensitivity and uncertainty analysis

The roadmap is tracked in GitHub Issues and Projects.

## Contributing

Contributions of all kinds are welcome: code, documentation, methodological review, test data, translations.

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
- Look for issues labelled `good first issue`.
- Be respectful: see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

SolidarityNode is licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0). See [LICENSE](LICENSE).

In short: you may use, study, modify and share the software, including offering services around it, but modified versions (including those run as a network service) must remain open under the same license.

The name "SolidarityNode" is not covered by the license. See the draft [trademark policy](TRADEMARK.md).

## Background

The framework draws on the literature on accessibility (Geurs & van Wee, 2004), social vulnerability (Cutter et al., 2003; Adger, 2006), community and system resilience (Holling, 1973; Bruneau et al., 2003; Norris et al., 2008), critical infrastructure interdependencies (Rinaldi et al., 2001), probabilistic graphical models (Pearl, 1988; Koller & Friedman, 2009; Murphy, 2002) and Digital Twins (Grieves & Vickers, 2017). A full reference list will be maintained in `docs/`.

---

## Περίληψη στα ελληνικά

Το **SolidarityNode** είναι ανοιχτό χωρικό πιθανοτικό πλαίσιο για την εκτίμηση της προσβασιμότητας, της λανθάνουσας κοινωνικής ανάγκης, της τρωτότητας και της ανθεκτικότητας δικτύων κοινωνικών υπηρεσιών (δομές υγείας, κοινωνικής φροντίδας κ.ά.). Χρησιμοποιεί Bayesian και Dynamic Bayesian Networks και ενημερώνει τις εκτιμήσεις του με πραγματικά δεδομένα λειτουργίας.

Η βασική μονάδα ανάλυσης είναι: **χωρική μονάδα × κοινωνική ομάδα × υπηρεσία × χρόνος**. Η δυσλειτουργία μιας δομής δεν ταυτίζεται με απώλεια υπηρεσίας για τον πληθυσμό, και η τρωτότητα διαχωρίζεται από την ανθεκτικότητα.

Το project βρίσκεται σε πρώιμο ερευνητικό στάδιο. Ο κώδικας είναι πάντα ανοιχτός (AGPL-3.0) και δεν περιλαμβάνει ποτέ πραγματικά δεδομένα, μόνο συνθετικά.
