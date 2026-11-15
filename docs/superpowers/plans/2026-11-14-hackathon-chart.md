# Hackathon Helm and interactive workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare a single-node hackathon Helm deployment with optional in-cluster PostgreSQL and Redis and an interactive local/Kubernetes workflow.

**Architecture:** Extend the existing SAM chart without removing external dependency support. Keep credentials in an externally created Kubernetes Secret; use distinct local and Kubernetes credential files and explicit confirmation for cluster mutations. The existing application remains a scaffold.

**Tech Stack:** Helm, Kubernetes, Bash, Docker Compose, pytest.

**Spec:** Approved design and subsequent changes in conversation: embedded PostgreSQL/Redis, Kubernetes PVCs, interactive dev.sh with local controls and separate preparation and deployment, Secret creation only after confirmation.

## Global Constraints

- One worker node; no HA claims; PVCs are not backups.
- Existing CLI commands remain compatible; no secrets in git, command arguments, or output.
- Never overwrite existing credentials or rotate database passwords implicitly; existing PVC initialization does not rotate passwords.
- No cloud mutations or real deployments during automated tests.
- Worker and migrations disabled for hackathon until implemented.
- External PostgreSQL and Redis remain supported; no actual production-readiness claim.

## Review Focus

- Existing PostgreSQL volume and changed credentials: refuse unsafe automatic rotation, explain recovery.
- Repeated Secret preparation: never silently overwrite cluster credentials.
- Noninteractive invocation and cancellation: no unintended deployment.
- Helm release names: web proxy resolves correct service names and strips prefixes.
- Redis persistence and PostgreSQL pgvector: configure and verify behavior, not PVC presence alone.

### Task 1: Stateful chart

**Files:** `deploy/helm/sam/values.yaml`, `deploy/helm/sam/values-hackathon.yaml`, new focused templates under `deploy/helm/sam/templates/`, `tests/test_helm_chart.py`.

**Interfaces:** Built-in PostgreSQL and Redis enabled in hackathon values, configurable storage classes and sizes; existing Secret supplies PostgreSQL credentials and application connection values. Service names are release-aware and consistent with script in task 3.

- [ ] Write tests rendering chart for internal/external modes, persistence, secret refs, Redis persistence configuration and worker/migrations disabled. Verify tests fail before implementation.
- [ ] Implement single-replica StatefulSets, ClusterIP Services, PostgreSQL initialization of vector extension for fresh volumes and PVC configuration. Preserve volume data on uninstall; document initialization and password rotation limitations.
- [ ] Run tests, `helm lint` and render both modes; confirm pass.

### Task 2: Application routing and startup

**Files:** `deploy/helm/sam/templates/`, `deploy/helm/sam/values-hackathon.yaml`, `tests/test_helm_chart.py`.

**Interfaces:** Web routes `/api/` and `/ingest/` to release-aware services preserving existing prefix-stripping behavior; existing Secret contract remains available.

- [ ] Add failing render tests for release-specific nginx upstreams and resource settings, and worker disabled.
- [ ] Fix web configuration via chart-managed config; keep Compose behavior unchanged and do not imply scaffold connects to databases.
- [ ] Verify render/lint and tests pass.

### Task 3: Interactive environment management

**Files:** `scripts/dev.sh`, `.env.example`, `.gitignore`, `tests/test_dev_script.py`.

**Interfaces:** Existing `env`, `up`, `down`, `restart`, `logs`, `status`, `config` stay compatible; no-argument interactive menu supports local env, up, stop, status and all/per-service logs; Kubernetes prepare and deploy are separate. Cluster Secret is created only after explicit confirmation and never silently overwritten. Local and Kubernetes credentials are separate.

- [ ] Write isolated tests with mocked commands for menu selection, abort, existing files/secrets, noninteractive use, and matching generated PostgreSQL credentials/URL; verify failures.
- [ ] Implement safe generation without printing secrets, protected files, non-evaluated env parsing and secret creation without credentials in process arguments. Confirm context/namespace/release before mutation; fail closed on missing inputs. Keep production/hackathon credentials separate.
- [ ] Run mocked tests and shell syntax checks; verify no actual cluster changes.

### Task 4: Documentation and integration verification

**Files:** `README.md`, `deploy/helm/sam/README.md`, tests as needed.

- [ ] Document exact manual setup, storage class check, registry requirements, image references, secrets, backup and Redis queue limitations, scaffold status, and local/Kubernetes menu.
- [ ] Run existing tests, chart tests, helm lint/template, shell syntax; report actual outputs and any unavailable cluster checks.
- [ ] Request independent review of whole diff, address significant findings, then report remaining deployment prerequisites without applying to cluster without explicit confirmation.
