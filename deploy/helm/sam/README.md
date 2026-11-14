# SAM Helm chart

This chart deploys the SAM scaffold as one release containing API, ingest, Celery worker, and web workloads. PostgreSQL and Redis are external by default. The optional `values-hackathon.yaml` enables single-replica built-in PostgreSQL and Redis and disables the unimplemented worker and migrations.

## Required secret

Create a Secret before installing and set `existingSecret` to its name. The Secret must contain keys for `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `AGENT_API_KEY`, and `OPENAI_API_KEY` (key names can be remapped with `secretKeys`). This chart never creates or stores Secret objects.

For the built-in PostgreSQL and Redis setup, run `./scripts/dev.sh` from the repository root and select **Prepare Kubernetes Secret**. Confirm the release, namespace, and context; the script creates a Secret named `<release>-sam-secrets` and stores credentials in a private local file. Keep that file safe. Select **Deploy Kubernetes** to install using `values-hackathon.yaml` and the same target. The generated connection URLs are for the built-in services, not external databases.

Alternatively, provision a Secret through your organization's secret manager before installation; avoid putting secret values in command arguments, shell history, or Helm values. For example, with external services and a Secret named `sam-secrets`, install with its name:

```sh
helm install sam ./deploy/helm/sam -f ./deploy/helm/sam/values-dev.yaml \
  --set existingSecret=sam-secrets
```

External database and Redis host/port/user/SSL settings are rendered into the chart ConfigMap. Adjust them in values files or with `--set`. For built-in services, host names use the release fullname with `-postgresql` and `-redis` suffixes and ports are 5432 and 6379 respectively, regardless of the external port values. With built-in PostgreSQL, workloads receive `DB_USER` directly from the existing Secret's `POSTGRES_USER` key instead of the ConfigMap. The Secret's `DATABASE_URL` and `REDIS_URL` must point to the intended services; the chart does not construct them.

## Built-in stateful services

For `values-hackathon.yaml`, also add `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` to the existing Secret. Their values must agree with `DATABASE_URL`. Built-in PostgreSQL does not configure TLS: `DB_SSLMODE` is `disable` when it is enabled; configure the separate `DATABASE_URL` accordingly (for example with `sslmode=disable`). External PostgreSQL continues to use `database.sslMode`. Use the built-in service only on a trusted network.

PostgreSQL runs the pgvector initialization script only when initializing a fresh volume. If initialization fails after the data directory is created, it will not automatically rerun on restart: the authenticated TCP readiness check remains unready until the configured database contains `vector`. Inspect the PostgreSQL logs and resolve the underlying error first. Back up the existing volume, then connect with an authorized database administrator to the configured database and run `CREATE EXTENSION IF NOT EXISTS vector;`; verify it exists in `pg_extension`. If the Secret credentials no longer match the database, restore access using valid existing administrator credentials before correcting the Secret. Do not delete the PVC merely to retry initialization. Changing the Secret does **not** rotate the database password; rotate credentials explicitly in PostgreSQL and update the Secret and connection URL in a coordinated maintenance operation. The chart does not configure a credential-dependent liveness probe that would restart PostgreSQL in this situation.

The PostgreSQL and Redis PVCs are retained on StatefulSet deletion or scale-down. Configure `postgresql.persistence.size`, `postgresql.persistence.storageClass`, `redis.persistence.size`, and `redis.persistence.storageClass` for your cluster. An empty storage class uses the cluster default. Redis enables append-only persistence; neither PVC retention nor Redis persistence is a backup or a high-availability guarantee. Built-in Redis has no authentication and should be restricted to trusted cluster workloads.

Helm render tests check configuration, not a live PostgreSQL login, extension initialization, Redis writes, or AOF recovery. Before relying on these services, test on an isolated deployment: verify authenticated PostgreSQL TCP access and the `vector` extension, write a disposable Redis key, restart Redis while retaining its PVC, and confirm the key returns. Also test restoration from independent backups; AOF and retained PVCs do not replace backups.

## Optional features

Ingress is disabled by default and routes all traffic through web when enabled; it requires `services.web.enabled=true`. Web proxies `/api/` and `/ingest/` with the prefix removed. Exact `/api` and `/ingest` return 404 rather than the SPA; a disabled API or ingest service returns 503 for its prefix. Configure `ingress.annotations` directly, or enable the configurable cert-manager ClusterIssuer annotation using `ingress.certManager.enabled` and `ingress.certManager.clusterIssuer`.

For API or ingest, changing `services.<name>.port` also requires changing `services.<name>.command` so that the application listens on the same port. The chart cannot infer the listening port from an arbitrary custom command. The default commands listen on 8000 and 8001 respectively; overriding only the port breaks connectivity. Web's nginx listen port follows `services.web.port`.

HPA, PDB, ServiceMonitor, image pull secrets, custom resources, security contexts, and service accounts are configurable in `values.yaml`.

Migration hooks are **disabled and unsupported**: the application scaffold has no migration implementation, and a pre-install hook cannot depend on the chart's ordinary ConfigMap or built-in database resources, which Helm creates after the hook. Enabling migrations fails chart rendering even if a command is supplied. Implement and review migrations and hook dependencies before adding support.

Use `values-dev.yaml` or `values-prod.yaml` as environment starting points. Replace example image repositories/tags and production hostnames before deployment.
