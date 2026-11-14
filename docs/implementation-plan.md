# План реализации SAMoparser (командный backlog)

> **Статус:** план работ для будущей реализации. Этот документ не утверждает, что какие-либо перечисленные сервисы, endpoints, миграции, тесты или deployment уже существуют. Цель — получить маленькие проверяемые increments без бизнес-реализации в scaffold.

## 1. Принципы выполнения

- Каждый этап заканчивается тестируемым вертикальным результатом и явным evidence.
- Сначала контракты, границы безопасности и наблюдаемость; бизнес-правила matching добавляются позже.
- Никаких claims «готово» без теста, review и проверки deploy-пути.
- Любая задача, затрагивающая PII, auth, SQL или миграции, требует security review.
- В production Kubernetes PostgreSQL и Redis — внешние сервисы; локальные аналоги применяются только для dev/test.

## 2. Этапы и backlog

### Этап 0 — согласование scaffold и ADR

**Цель:** зафиксировать решения до кода.

- [ ] Назначить владельцев компонентов и threat model review.
- [ ] Утвердить API `v1`, tenant model, роли и scopes.
- [ ] Утвердить формат документов, retention, PII policy и human-review policy.
- [ ] Выбрать PostgreSQL vector extension либо отдельный vector store; определить lexical fallback.
- [ ] Зафиксировать AI provider contract, VK Cloud TLS requirements, timeouts и data minimization.
- [ ] Провести лицензирование зависимостей, моделей и датасетов; завести risk register.

**Проверка выхода:** подписанные ADR/контракты и список открытых рисков; кодовая реализация не требуется.

### Этап 1 — репозиторный и локальный каркас

**Цель:** воспроизводимые процессы без бизнес-логики.

- [ ] Создать каталоги/пакеты `backend`, `ingest`, `web`, `worker` только в рамках отдельной реализации.
- [ ] Добавить конфигурационную схему с безопасными defaults, redaction и проверкой обязательных env.
- [ ] Подготовить local dev profile с временными PostgreSQL/Redis; не путать его с production topology.
- [ ] Определить structured logging, `request_id`, `correlation_id`, health/readiness semantics.
- [ ] Добавить contract-test harness и статические проверки.

**Проверка выхода:** локальный smoke запускает пустые health endpoints и подключается к зависимостям; бизнес-операции ещё недоступны.

### Этап 2 — безопасность доступа и API skeleton

- [ ] Реализовать JWT verification с фиксированным algorithm, issuer, audience, expiry и key rotation.
- [ ] Реализовать API-key issuance/rotation/revocation: хранить только hash, plaintext показать один раз.
- [ ] Добавить tenant и scope middleware, deny-by-default, rate limits и безопасные error codes.
- [ ] Описать OpenAPI для auth, health и пустых resource contracts.
- [ ] Добавить тесты: expired/forged JWT, wrong audience, revoked key, cross-tenant object, scope escalation, log redaction.

**Проверка выхода:** auth/security tests проходят; endpoints, меняющие данные, ещё могут быть заглушками с явным `501 Not Implemented`.

### Этап 3 — БД и миграции

- [ ] Реализовать SQLAlchemy/эквивалент модели для tenants, users, api_keys, sources, ingest_batches, documents, chunks, entities, candidates, embeddings, jobs, audit_events.
- [ ] Создать первую миграцию и индексы: tenant boundaries, idempotency uniqueness, job uniqueness, audit indexes.
- [ ] Добавить PostgreSQL RLS policies и read-only/reporting views; проверить отсутствие cross-tenant rows.
- [ ] Определить migration compatibility rules: expand/contract, forward/backward app compatibility.
- [ ] Написать migration tests на чистой и обновляемой БД, включая rollback policy там, где rollback безопасен.
- [ ] Подготовить backup/restore smoke и retention checks.

**Важное ограничение:** migration hook в Kubernetes **оставить отключённым до появления этой реальной миграционной реализации и review**. После review добавить отдельный locked migration Job, а не startup hook каждого pod.

**Проверка выхода:** миграции воспроизводимо поднимают схему в test DB, RLS и уникальные ограничения доказаны тестами, backup restore подтверждён.

### Этап 4 — идемпотентный ingest

- [ ] Реализовать upload/reference validation: MIME, size, extension, checksum, anti-zip-bomb и retention.
- [ ] Реализовать `Idempotency-Key` с tenant/source scope и конфликтом при другом payload.
- [ ] Ввести transactional outbox или эквивалент: job публикуется только после commit.
- [ ] Реализовать batch/document/job state machine и safe retry.
- [ ] Добавить property/integration tests: повтор запроса, concurrent duplicate, crash after commit, retry after worker timeout, partial batch.
- [ ] Добавить quarantine path для невалидных/подозрительных объектов и audit events.

**Проверка выхода:** один и тот же ingest не создаёт дублей при последовательных и конкурентных повторах; status API объясняет результат.

### Этап 5 — parsing, normalization и PII

- [ ] Реализовать parser adapters с ограничением ресурсов и версией parser.
- [ ] Нормализовать encoding, whitespace, language, identifiers и canonical forms.
- [ ] Реализовать PII classification/masking policy перед внешним AI provider.
- [ ] Сохранять исходник по retention policy, chunk checksum и parser metadata.
- [ ] Добавить fixture tests для поддержанных форматов, malformed input, PII redaction и determinism.

**Проверка выхода:** fixtures дают воспроизводимый normalized output, ошибки не раскрывают исходный секретный текст в логах.

### Этап 6 — matching pipeline и vectors

- [ ] Реализовать chunking и embedding adapter с timeout, bounded retry и model/version metadata.
- [ ] Подключить vector retrieval; выбрать и измерить lexical fallback.
- [ ] Реализовать candidate scoring/reranking с конфигурируемыми thresholds и `needs_review`.
- [ ] Ввести human decision endpoint, audit и неизменяемую историю decisions.
- [ ] Добавить golden dataset (обезличенный), precision/recall metrics, threshold tests и degraded-provider tests.
- [ ] Проверить TLS certificate/hostname verification для VK Cloud; запрещать insecure fallback.

**Проверка выхода:** pipeline воспроизводим на golden fixtures, provider outage не теряет jobs, fallback явно маркирован, AI не изменяет canonical entity без decision.

### Этап 7 — безопасный text-to-SQL / аналитика

- [ ] Сначала реализовать report registry/JSON AST; не принимать произвольный SQL как публичный контракт.
- [ ] Добавить allowlist полей, параметризацию, AST validation и лимиты результата.
- [ ] Создать отдельную read-only DB role, views и RLS; изолировать connection pool.
- [ ] Настроить `statement_timeout`, `lock_timeout`, row/result limits и запрет multi-statements/unsafe functions.
- [ ] Написать negative tests для injection, cross-tenant predicates, DDL/DML, comments, COPY, expensive query и prompt injection.
- [ ] Добавить audit и preview; нарушение policy должно давать отказ.

**Проверка выхода:** adversarial suite показывает, что сгенерированное намерение не обходит DB-level controls; прямое исполнение модельного SQL не разрешено.

### Этап 8 — web и публичная эксплуатация

- [ ] Реализовать web :8080 как клиент backend :8000, без прямого доступа к БД/AI.
- [ ] Добавить состояния loading, empty, failed, degraded и human review; не выдавать AI suggestion как факт.
- [ ] Проверить CSRF/CORS/cookie policy, XSS-safe rendering и upload UX limits.
- [ ] Добавить browser/component tests для auth, ingest status, candidate decision и error states.

**Проверка выхода:** browser tests подтверждают только разрешённые API-вызовы и понятные degraded states.

### Этап 9 — Kubernetes deployment и эксплуатация

- [ ] Подготовить отдельные manifests/Helm values для `backend :8000`, `ingest :8001`, `web :8080`, Celery worker/beat.
- [ ] Подключить внешние PostgreSQL и Redis через secrets, TLS, NetworkPolicy и connection limits.
- [ ] Добавить liveness/readiness, resource requests/limits, PDB, graceful shutdown и bounded worker concurrency.
- [ ] Включить миграционный Job только после завершения этапа 3 и отдельного approval; до этого migration hook disabled.
- [ ] Настроить Ingress/TLS, backup/restore procedure и smoke deploy в staging.
- [ ] Не включать HPA, пока не определены queue lag, latency и saturation metrics.

**Проверка выхода:** staging deploy, migration/rollback drill, dependency outage drill, queue retry drill и проверка секретов проходят по runbook.

### Этап 10 — release readiness

- [ ] Провести security review и dependency/license scan; сформировать SBOM и NOTICE после юридического решения.
- [ ] Выполнить load, soak, failure-injection и restore tests на обезличенных данных.
- [ ] Проверить SLO/SLI: API latency/error rate, ingest success, queue lag, match quality, fallback rate, provider errors.
- [ ] Провести privacy review, data deletion/retention test и audit sampling.
- [ ] Подписать risk acceptance для остаточных рисков; подготовить incident/runbook и rollback plan.
- [ ] Запросить code review и зафиксировать evidence каждого gate.

**Проверка выхода:** release candidate может быть выдвинут только после доказательств, а не по наличию контейнерных manifests.

## 3. Приоритеты и зависимости

```text
ADR/security contracts
        -> API/auth skeleton
        -> DB schema + migration tests
        -> ingest idempotence
        -> parsing/PII
        -> matching/vectors
        -> safe analytics
        -> web polish
        -> staging/deploy/release
```

Параллельно после этапа 1 можно вести документацию API, threat modeling и подготовку fixtures. Matching нельзя считать готовым без ingest, версионирования и audit. Deployment нельзя считать готовым до migration/backup/restore checks; при этом migration hook остаётся выключенным до появления реализации миграций.

## 4. Definition of Done для любой задачи

1. Контракт и границы ответственности обновлены.
2. Есть автоматический тест или воспроизводимый verification command.
3. Ошибки, retry и audit behavior определены.
4. Нет секретов/PII в логах, fixtures и examples.
5. Для DB/API/security изменений выполнен review соответствующего владельца.
6. Документировано, что реально сделано, а что остаётся scaffold/TODO.

## 5. Явное состояние на момент написания

В этом репозитории данный файл и `docs/architecture.md` являются планом и архитектурным предложением. Наличие документов не означает наличия backend, ingest, web, Celery, Redis/PostgreSQL схемы, API, AI matching, vector fallback, безопасного text-to-SQL, Kubernetes deployment или миграций. Любые такие утверждения допустимы только после выполнения соответствующих этапов и проверки evidence.
