# SAM Helm chart

This chart deploys the SAM scaffold as one release containing API, ingest, Celery worker, and web workloads. PostgreSQL and Redis are external dependencies; this chart intentionally does not provision them.

## Required secret

Create a Secret before installing and set `existingSecret` to its name. The Secret must contain keys for `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `AGENT_API_KEY`, and `OPENAI_API_KEY` (key names can be remapped with `secretKeys`). This chart never creates or stores Secret objects.

```sh
kubectl create secret generic sam-secrets \
  --from-literal=DATABASE_URL='postgresql://...' \
  --from-literal=REDIS_URL='redis://...' \
  --from-literal=JWT_SECRET='...' \
  --from-literal=AGENT_API_KEY='...' \
  --from-literal=OPENAI_API_KEY='...'
helm install sam ./deploy/helm/sam -f ./deploy/helm/sam/values-dev.yaml \
  --set existingSecret=sam-secrets
```

Non-secret database and Redis host/port/user/SSL settings are rendered into the chart ConfigMap. Adjust them in values files or with `--set`.

## Optional features

Ingress is disabled by default and exposes `/api`, `/ingest`, and `/` routes when enabled. Configure `ingress.annotations` directly, or enable the configurable cert-manager ClusterIssuer annotation using `ingress.certManager.enabled` and `ingress.certManager.clusterIssuer`.

HPA, PDB, ServiceMonitor, image pull secrets, custom resources, security contexts, and service accounts are configurable in `values.yaml`.

Migration pre-install/pre-upgrade hooks are **disabled by default** because the application scaffold has no migration implementation. To use them later, set `migrations.enabled=true` and provide an explicit `migrations.command`; no migration command is assumed by this chart.

Use `values-dev.yaml` or `values-prod.yaml` as environment starting points. Replace example image repositories/tags and production hostnames before deployment.
