# План реализации SAMoparser (командный backlog)

> **Статус:** рабочий план команды. Отмеченные выполненными пункты проверены в репозитории; незавершённые задачи не следует считать реализованными.

## Текущий статус после первой проверки

Ветка разработки: `test`. Проект уже прошёл первую промежуточную проверку менторов.

| Область | Фактическое состояние |
|---|---|
| Локальный запуск | Docker Compose запускает API, ingest, PostgreSQL, Redis и web; миграция выполняется отдельным сервисом. |
| Backend API | Есть каталог ПО, компьютеры, установки, импорт JSON/CSV, риски, сводка, ручное сопоставление и удаление. |
| Хранилище | SQLAlchemy и Alembic; есть таблицы ПО, устройств, установок и заготовка событий риска. |
| Тестовые данные | `make seed` загружает данные кейса из Excel: около 24,5 тыс. установок. |
| Frontend | Есть русскоязычный dashboard; отдельные страницы каталога, компьютеров и установок ещё не реализованы. |
| Безопасность | Авторизация, роли, tenant-изоляция, RLS и аудит действий не реализованы. |
| Обработка данных | Базовая нормализация, exact matching, файловый импорт и Idempotency-Key; fuzzy matching и очередь ручной проверки ещё впереди. |

## Единый план локального MVP

Этот раздел — единый рабочий источник истины после интеграции всех направлений
разработки. Production/VK Cloud задачи не являются блокерами локального MVP.

| Фаза | Содержание | Статус |
|---|---|---|
| 0 | ADR, baseline, словарь данных и границы честности | [~] Начата: ADR и baseline добавлены |
| 1 | Нормализация, alias/fuzzy matching, кандидаты и read-only review queue | [ ] Следующая фаза |
| 2 | Approve/reject/reopen, append-only история и review UI | [ ] |
| 3 | Модель лицензий, соглашения, связи, права, seed фактов Excel | [ ] |
| 4 | Страница лицензий, агрегаты и demo overlay | [ ] |
| 5 | SQL-расчёт рисков, пагинация, фильтры и risk UI | [ ] |
| 6 | AI Smart Matching reranker с mock/fallback и human approval | [ ] |
| 7 | Локальная демонстрация, performance evidence и документация | [ ] |

### Зафиксированные правила

- Excel не считается реестром закупок. В нём нет подтверждённых количеств,
  стоимости, сроков, метрик лицензирования и назначений.
- `null` означает «неизвестно», а не нулевое количество.
- Обязательный seed не создаёт выдуманные закупки, права или сроки.
- Лицензии разделяются на соглашения, связи продукта с соглашением и реальные
  права/закупки.
- Matching проходит путь `exact → alias → fuzzy → AI suggestion → human decision`.
- Только человек через decision API может изменить каноническое сопоставление
  после fuzzy/AI-рекомендации.
- AI по умолчанию отключён или работает через локальный mock; он не получает
  `computer_id`, пользователя и другие PII.
- Риски и списочные endpoint’ы не должны загружать весь массив из 24,5 тыс.
  установок в Python.

### Baseline источника и локальной базы

Запуск:

```bash
make baseline
```

Ожидаемые факты источника Excel: 24 589 установок, 187 устройств, 29 уникальных
продуктов, 47 строк каталога, 32 названия соглашений. На момент baseline локального
volume после ручных smoke-проверок было 24 590 установок и 189 устройств; эти две
дополнительные записи не являются данными Excel. Полный вывод и ограничения
зафиксированы в [`docs/baseline.md`](baseline.md).

### Ближайшая задача

**Фаза 1 — matching и read-only очередь проверки.** Сначала нужно вынести нормализацию
из `api.py`, добавить структурированный результат матчинга, aliases, fuzzy-оценку,
пороги и кандидатов. До подтверждения человеком установки не получают новое
каноническое сопоставление.

### Очередность ближайшей работы

1. [x] Пагинация установок; файловый импорт и Idempotency-Key.
2. [~] Baseline, ADR и фиксация честности данных.
3. [ ] Matching v1: нормализация, aliases, fuzzy и golden dataset.
4. [ ] Review workflow: approve/reject/reopen и история решений.
5. [ ] License facts: соглашения, связи, права и честный `no_data`.
6. [ ] SQL-риски, лицензии и dashboard без полного Python-сканирования.
7. [ ] AI Smart Matching, локальное demo и performance evidence.

Для хакатонного MVP эти задачи важнее полного enterprise-набора tenant/RLS, text-to-SQL и vector DB; последние остаются перспективными этапами, а не заявленной текущей функциональностью.

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

- [x] Создать каталоги/пакеты `backend`, `ingest`, `web`, `worker`.
- [~] Добавить конфигурационную схему и проверку обязательных env; redaction и fail-closed production configuration ещё требуются.
- [x] Подготовить локальный профиль Docker Compose с PostgreSQL/Redis; production topology отделена в Helm.
- [~] Определить health/readiness (`/health`, `/ready`); structured logging, `request_id` и `correlation_id` ещё отсутствуют.
- [~] Добавить pytest-проверки scaffold и бизнес-среза; полноценный OpenAPI contract-test harness ещё требуется.

**Проверка выхода:** локальный smoke запускает пустые health endpoints и подключается к зависимостям; бизнес-операции ещё недоступны.

### Этап 2 — безопасность доступа и API skeleton

- [ ] Реализовать JWT verification с фиксированным algorithm, issuer, audience, expiry и key rotation.
- [ ] Реализовать API-key issuance/rotation/revocation: хранить только hash, plaintext показать один раз.
- [ ] Добавить tenant и scope middleware, deny-by-default, rate limits и безопасные error codes.
- [ ] Описать OpenAPI для auth, health и пустых resource contracts.
- [ ] Добавить тесты: expired/forged JWT, wrong audience, revoked key, cross-tenant object, scope escalation, log redaction.

**Проверка выхода:** auth/security tests проходят; endpoints, меняющие данные, ещё могут быть заглушками с явным `501 Not Implemented`.

### Этап 3 — БД и миграции

- [~] Реализовать SQLAlchemy-модели для каталога ПО, компьютеров и установок; tenants, users, sources, batches, jobs и audit ещё отсутствуют.
- [~] Создать Alembic-миграции для базовых SAM-сущностей; индексы идемпотентности и аудита ещё отсутствуют.
- [ ] Добавить PostgreSQL RLS policies и read-only/reporting views; проверить отсутствие cross-tenant rows.
- [ ] Определить migration compatibility rules: expand/contract, forward/backward app compatibility.
- [ ] Написать migration tests на чистой и обновляемой БД, включая rollback policy там, где rollback безопасен.
- [ ] Подготовить backup/restore smoke и retention checks.

**Важное ограничение:** migration hook в Kubernetes **оставить отключённым до появления этой реальной миграционной реализации и review**. После review добавить отдельный locked migration Job, а не startup hook каждого pod.

**Проверка выхода:** миграции воспроизводимо поднимают схему в test DB, RLS и уникальные ограничения доказаны тестами, backup restore подтверждён.

### Этап 4 — идемпотентный ingest

- [x] Реализован обязательный multipart-upload CSV/JSON, проверка расширения, UTF-8, структуры и лимит 10 МБ. Архивы не принимаются, поэтому zip-bomb не актуален; checksum полного файла и retention ещё отсутствуют.
- [~] Реализован `Idempotency-Key` с SHA-256 отпечатком нормализованного содержимого, безопасным повтором и `409` при другом содержимом. Tenant/source scope и защита конкурентной вставки ещё не реализованы.
- [ ] Ввести transactional outbox или эквивалент: job публикуется только после commit.
- [ ] Реализовать batch/document/job state machine и безопасный повтор обработки.
- [ ] Добавить property/integration tests: повтор запроса, concurrent duplicate, crash after commit, retry after worker timeout, partial batch.
- [ ] Добавить quarantine path для невалидных/подозрительных объектов и audit events.

**Проверка выхода:** один и тот же ingest не создаёт дублей при последовательных и конкурентных повторах; status API объясняет результат.

### Завершённый инкремент — пагинация установок

- [x] `GET /api/v1/installations` возвращает `{items, total, limit, offset}`.
- [x] Поддерживается фильтр `status` (`matched`/`unknown`).
- [x] Ограничение размера страницы: 1–500 записей; отрицательный offset отклоняется.
- [x] Добавлен тест порядка, фильтра, метаданных страницы и недопустимых параметров.
- [x] Проверено на тестовой базе: 24 589 установок, выборка страницы через API и nginx успешна.

### Завершённый инкремент — файловый импорт установок

- [x] Обе ручки импорта требуют поле `file` в `multipart/form-data`; передача CSV-текста параметром или JSON-массивом в API больше не является контрактом загрузки.
- [x] Общая ручка принимает `.csv` и `.json`; специализированная CSV-ручка также принимает только загружаемый `.csv`-файл.
- [x] Добавлены ограничения размера файла (10 МБ), проверка UTF-8, пустого файла, расширения и структуры данных.
- [x] Повтор с тем же `Idempotency-Key` и тем же содержимым возвращает сохранённую сводку и не создаёт установки повторно; другой payload с тем же ключом даёт `409`.
- [x] Добавлены таблица `import_batches` и связь с установками; миграции применены, `alembic check` подтверждает отсутствие расхождений.
- [x] API-тестами проверены обязательность файла, CSV/JSON, неподдерживаемый формат, повторный импорт и конфликт ключа.

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
- [~] Dashboard и состояние загрузки/API реализованы; отдельные экраны установок/каталога, empty/failed/degraded и human review ещё нужны.
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

Реализованы локальный backend/frontend-каркас, PostgreSQL-модели и миграции для базовых SAM-сущностей, загрузка тестовых данных и первый рабочий API/dashboard-срез. Celery worker пока только подключён к Redis и не выполняет прикладные задачи. AI matching, векторный поиск, аутентификация, tenant/RLS, аудит, безопасная аналитика и production-развёртывание остаются задачами плана. Следующее изменение плана и кода должно начинаться с пагинации инвентаря и тестов API-контракта.
