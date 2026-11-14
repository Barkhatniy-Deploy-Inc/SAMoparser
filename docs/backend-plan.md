# Персональный план разработки Backend (`services/backend`) — SAMoparser

**Кейс:** Интеллектуальная система учёта и комплаенса ПО (SAM) — ПУ «СургутАСУнефть» (ПАО «Сургутнефтегаз»)  
**Команда:** Бархатный деплой  
**Зона ответственности:** Backend (`api :8000`, `ingest :8001`, `worker`, PostgreSQL + `pgvector`, Redis, интеграция AI-модулей)

---

## Целевая структура пакета `services/backend/`

Все три процесса (`app.api:app`, `app.ingest:app`, `app.worker:celery_app`) собираются из одного Docker-образа и переиспользуют единое ядро моделей и бизнес-логики:

```text
services/backend/
├── Dockerfile
├── requirements.txt             # Строго с пинами версий '==' (проверяется в tests/test_scaffold.py)
├── alembic.ini
├── migrations/                  # Миграции Alembic + аналитические SQL Views
└── app/
    ├── api.py                   # Entrypoint :8000 (основной REST API для UI)
    ├── ingest.py                # Entrypoint :8001 (импорт CSV и приём отчётов агентов)
    ├── worker.py                # Entrypoint Celery (фоновый ИИ-разбор процессов и EULA)
    ├── core/                    # Конфиг, логирование, JWT/API-key auth, обработчики ошибок
    ├── db/                      # SQLAlchemy Engine, сессии (R/W + Read-Only для ИИ), Base
    ├── models/                  # SQLAlchemy 2.0 модели предметной области SAM
    ├── schemas/                 # Pydantic v2 схемы запросов и ответов (OpenAPI контракт для фронта)
    ├── repositories/            # Слой запросов к БД и батчевых идемпотентных upsert-операций
    ├── services/                # Доменная логика (Compliance Engine, CSV-парсер, сверка снимков)
    ├── ai/                      # Универсальный LLM/Embedding клиент + 3 ИИ-модуля + фолбэки
    ├── routers/                 # FastAPI роутеры по доменам
    └── seed/                    # Наполнение БД эталоном БПО Сургутнефтегаза и демо-рисками
```

---

## Модуль 0. Подготовка фундамента и устранение ловушек текущего каркаса

### 0.1. Зависимости и совместимость импортов (`Docker` vs локальный `pytest`)
- [ ] **0.1.1.** Обновить `services/backend/requirements.txt`, фиксируя каждую зависимость строго через `==` (тест `test_backend_has_shared_image_and_pinned_dependencies` в `tests/test_scaffold.py` упадёт без `==`):
  - `celery==5.4.0`, `fastapi==0.115.6`, `uvicorn[standard]==0.34.0`
  - `sqlalchemy==2.0.36`, `psycopg[binary]==3.2.3`, `alembic==1.14.0`, `pgvector==0.3.6`
  - `pydantic-settings==2.6.1`, `python-multipart==0.0.19`
  - `pyjwt==2.10.1`, `pwdlib[argon2]==0.2.1` (или `bcrypt==4.2.1`)
  - `httpx==0.28.1`, `openai==1.57.0` (совместим с OpenAI, `vLLM`, `Ollama` в VK Cloud)
  - `pypdf==5.1.0` (извлечение текста из PDF с лицензионными соглашениями)
- [ ] **0.1.2.** Добавить в корень репозитория `pyproject.toml` с настройками `pytest` (`pythonpath = [".", "services/backend"]`) и `ruff`, чтобы импорты `from app...` одинаково работали и внутри контейнера (`PYTHONPATH=/app/services/backend`), и при локальном `make test`.
- [ ] **0.1.3.** Сохранить служебные маршруты `/healthz`, `/readyz`, `/metrics` на обоих приложениях (`api.py` и `ingest.py`) для совместимости с `tests/test_scaffold.py` и пробами Kubernetes.

### 0.2. Конфигурация и переменные окружения (`app/core/config.py`)
- [ ] **0.2.1.** Создать отсутствующий в репозитории `.env.example` (необходим для работы `./scripts/dev.sh env`).
- [ ] **0.2.2.** Реализовать `Settings(BaseSettings)` через `pydantic-settings`:
  - Поддержка `DATABASE_URL` напрямую (как в K8s Secret), а если переменная не задана (как в текущем `docker-compose.yml`) — автоматическая сборка строки подключения из `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`.
  - Настройки `REDIS_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES=720`, `AGENT_API_KEY`.
  - Настройки ИИ: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `AI_TIMEOUT_SECONDS=15`.
  - Пороги бизнес-логики: `ZOMBIE_INACTIVE_DAYS=90`, `MATCH_AUTO_THRESHOLD=0.85`, `MATCH_REVIEW_THRESHOLD=0.55`.

### 0.3. Выравнивание роутинга, CORS и Healthchecks (синхронизация с фронтом и DevOps)
- [ ] **0.3.1.** Устранить расхождение путей между `services/web/nginx.conf` (где `proxy_pass http://api:8000/;` со слэшем срезает префикс `/api/`) и K8s Ingress (`deploy/helm/sam/templates/ingress.yaml`, который проксирует `/api` без обрезки):
  - Все бизнес-роуты `api` монтировать под `/api/v1/...`, роуты `ingest` — под `/ingest/v1/...`;
  - Согласовать с Яриком и Матвеем удаление завершающего слэша в `nginx.conf` (`proxy_pass http://api:8000;` и `proxy_pass http://ingest:8001;`), сохранив совместимость с `test_scaffold.py`.
- [ ] **0.3.2.** Подключить `CORSMiddleware` в `api.py` и `ingest.py` для локальной разработки фронтенда на Vite (`localhost:5173`).
- [ ] **0.3.3.** Исправить проблему `HEALTHCHECK` в `Dockerfile` (сейчас он жёстко проверяет `:8000/healthz`, что ломает контейнеры `ingest:8001` и `worker`): задать индивидуальные `healthcheck` в `docker-compose.yml` для `api`, `ingest` и `worker`.
- [ ] **0.3.4.** Реализовать реальную проверку зависимостей в `/readyz` (`SELECT 1` в PostgreSQL и `PING` в Redis с коротким таймаутом).
- [ ] **0.3.5.** Настроить единый формат JSON-ошибок (`{"error": {"code": "...", "message": "...", "details": ...}}`) и middleware сквозного `X-Request-ID`.

---

## Модуль 1. Слой БД, доменные модели SAM и миграции

### 1.1. Подключение к PostgreSQL + `pgvector` (`app/db/session.py`)
- [ ] **1.1.1.** Настроить SQLAlchemy 2.0 `engine` (`pool_pre_ping=True`), фабрику сессий `SessionLocal` и зависимость `get_db()`.
- [ ] **1.1.2.** Настроить отдельную фабрику **`ReadOnlySessionLocal`** (`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, `SET LOCAL statement_timeout = '3000ms'`) для безопасного исполнения аналитических SQL-запросов Чат-ассистента (Модуль 9).
- [ ] **1.1.3.** Описать базовый `Base` и миксин `TimestampMixin` (`created_at`, `updated_at` в UTC).

### 1.2. Модели каталога ПО и лицензий (`app/models/catalog.py`)
- [ ] **1.2.1.** Модель **`License`** (`licenses` — справочник лицензионных соглашений):
  - `id`, `name` (уникальное каноническое имя), `short_code` (`GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `MIT`, `BSD-3`, `MS-VL`).
  - Двойная классификация под оба документа ТЗ:
    - `cost_category`: Enum `free | paid | conditional_free` (бесплатные / платные / условно бесплатные — по презентации);
    - `license_type`: Enum `open_source | commercial | trial | freeware` (по PDF ТЗ).
  - Поля юридических рисков: `commercial_use_allowed: bool | None`, `copyleft_risk: Enum(none, weak, strong_viral)`, `has_hidden_subscriptions: bool`, `telemetry_risk: bool`, `restrictions_summary: Text | None`.
  - `eula_text: Text | None`, `ai_analysis_json: JSONB | None`, `analyzed_at: datetime | None`.
- [ ] **1.2.2.** Модель **`SoftwareCatalog`** (`software_catalog` — эталонный каталог ПО компании):
  - `id`, `canonical_name`, `vendor`.
  - `version_policy_raw: str | None` (под реальные записи Сургутнефтегаза: *«3.0.6 для Windows, 2.10.38 для Альт»*, *«24.22.1 для существующих проектов, 26.12.1 для новых»*).
  - `min_allowed_version: str | None` (для автоматической проверки устаревания версий).
  - `purpose: Text | None` («Краткое назначение БПО» из перечня заказчика).
  - Классификатор Минцифры РФ (`reestrpo`): `registry_section` (напр., `04 - Средства разработки программного обеспечения`), `registry_class` (напр., `04.04 - Среды разработки, тестирования и отладки`), `in_russian_registry: bool`.
  - Внутренняя категория компании: `company_status`: Enum `actual | deprecated | forbidden` (Актуальный / Устаревший / Запрещённый).
  - `licensing_metric`: Enum `per_device | per_user | unlimited`.
  - `embedding: Vector(dim) | None` — векторное представление карточки ПО для Smart Matching.
- [ ] **1.2.3.** Таблица связи **`software_licenses`** (`M:N` между `software_catalog` и `licenses`, так как у `MediaWiki` и `PDFCreator` в перечне заказчика указано по несколько лицензий одновременно).
- [ ] **1.2.4.** Модель **`SoftwareAlias`** (`software_aliases` — словарь известных имён процессов и синонимов):
  - `id`, `raw_pattern` (в нижнем регистре, уникальный индекс: `chrome.exe`, `google_chrome_v2`, `1cv8c.exe`), `software_id` (FK → `software_catalog`), `source`: Enum `seed | rule | ai_confirmed | manual`.
- [ ] **1.2.5.** Модель **`LicenseContract`** (`license_contracts` — закупки и квоты мест):
  - `id`, `software_id` (FK), `license_id` (FK, nullable), `contract_number`, `purchased_seats: int`, `unit_price_rub: Numeric(12, 2)`, `valid_from: date | None`, `valid_until: date | None`, `department_scope: str | None`, `is_active: bool`.

### 1.3. Модели сотрудников, хостов и инсталляций (`app/models/inventory.py`)
- [ ] **1.3.1.** Модель **`Employee`** (`employees` — сотрудники):
  - `id`, `tab_number`, `full_name`, `email`, `department`, `position`, `status`: Enum `active | dismissed | role_changed`, `status_changed_at: datetime | None`.
- [ ] **1.3.2.** Модель **`Host`** (`hosts` — рабочие станции и серверы):
  - `id`, `hostname` (уникальный индекс без учёта регистра), `ip_address`, `os_family`: Enum `windows | alt_linux | astra_linux | linux_other | macos`, `os_version`, `employee_id` (FK → `employees`, nullable), `department`, `last_seen_at: datetime`.
- [ ] **1.3.3.** Модель **`InstalledSoftware`** (`installed_software` — факты установленного/запущенного ПО):
  - `id`, `host_id` (FK → `hosts`, cascade), `raw_name`, `raw_version`, `raw_vendor`, `executable_path`, `detected_at`, `last_used_at: datetime | None`, `usage_minutes_30d: int | None`.
  - `ingest_source`: Enum `csv | agent | manual`, `batch_id` (FK → `ingest_batches`, nullable).
  - Поля мэтчинга: `matched_software_id` (FK → `software_catalog`, nullable), `match_status`: Enum `matched | needs_review | unmatched`, `match_method`: Enum `exact | normalized | alias | vector | llm | manual | none`, `match_confidence: float`, `ai_suggested_software_id` (FK → `software_catalog`, nullable), `ai_reasoning: str | None`.
  - `UniqueConstraint("host_id", "raw_name", "raw_version")` — гарантия отсутствия дублей при повторном импорте CSV и отчётах агента.
- [ ] **1.3.4.** Модель **`IngestBatch`** (`ingest_batches` — журнал импортов и синхронизаций):
  - `id`, `source_type` (`csv | agent`), `filename`, `file_sha256`, `status` (`processing | completed | failed`), `total_rows`, `matched_count`, `review_count`, `unmatched_count`, `error_message`, `created_at`.

### 1.4. Миграции Alembic и аналитические SQL Views
- [ ] **1.4.1.** Настроить `alembic.ini` и `migrations/env.py`; в первой миграции активировать `CREATE EXTENSION IF NOT EXISTS vector;` и создать все таблицы и индексы.
- [ ] **1.4.2.** Создать SQL-представления `v_software_compliance` и `v_host_risks` для быстрых агрегаций дашборда и безопасного Text-to-SQL.
- [ ] **1.4.3.** Реализовать цель `make migrate` в `Makefile`.

---

## Модуль 2. Сидирование реальных данных Сургутнефтегаза и демо-кейсов (`app/seed`)

### 2.1. Перенос эталонных справочников из PDF кейса
- [ ] **2.1.1.** Загрузить в `app/seed/surgut_bpo_data.py` все ~33 лицензионных соглашения из `Пример_перечня_лицензий.pdf` (`GNU GPL v.2/v.3`, `GNU LGPL`, `GNU Affero GPL v.3`, `MIT`, `BSD 3-clause`, `BSD 2-clause`, `PostgreSQL`, `Apache 2.0`, `EPL 2.0`, `MPL 2.0`, `PDFCreator Freeware`, `Nvidia EULA`, `Devart EULA` и др.) с нормализацией опечаток исходника.
- [ ] **2.1.2.** Загрузить все уникальные продукты БПО из `Пример_перечня_софта.pdf` (`Debugging Tools for Windows`, `TortoiseHg`, `MiKTeX`, `Cppcheck`, `GIMP`, `Glassfish`, `MediaWiki`, `PDFCreator`, `Python`, `Far Manager 3`, `VirtualBox`, `InkScape`, `Apache NetBeans`, `TortoiseSVN`, `Graphviz`, `pgAdmin 3`, `Archi`, `CMake`, `pgRouting`, `PostGIS`, `dBeaver Community Edition`, `MS Visual Studio Express 2015`, `Git`, `Node.js`, `Nvidia CUDA`, `IntelliJ IDEA CE`, `Liberica JDK`) с разделами/классами Минцифры и связями `M:N` к лицензиям.

### 2.2. Добавление коммерческого, российского и запрещённого ПО под сценарии защиты
- [ ] **2.2.1.** Добавить платный софт и договоры закупок (`license_contracts`):
  - `Microsoft Office Профессиональный плюс 2021` — куплено **100** мест по `38 000 ₽`, фактически установлено на **120** ПК (прямая демонстрация примера из ТЗ: дефицит 20 лицензий / риск `760 000 ₽`).
  - `Adobe Photoshop CC` — куплено **15** мест по `65 000 ₽`, установлено на **19** ПК (4 нелицензионные установки под вопрос чат-бота из ТЗ *«У кого стоит нелицензионный Photoshop?»*).
  - `1С:Предприятие 8.3 Клиент` — куплено **80** мест по `25 000 ₽`, активно используется 43, ещё **12** числятся за уволенными/сменившими роль сотрудниками или не запускались > 120 дней («зомби-софт» на `300 000 ₽`).
  - `КОМПАС-3D v22`, `МойОфис Стандартный`, `Astra Linux Special Edition`, `Kaspersky Endpoint Security` — позиции из Реестра российского ПО (`in_russian_registry=True`).
- [ ] **2.2.2.** Добавить условно-бесплатное и ограниченное ПО (`conditional_free` / `trial`):
  - `TeamViewer Free (Personal Use Only)` в корпоративной сети (`commercial_use_allowed=False` — юридический риск из презентации);
  - `WinRAR Trial` с истёкшим тестовым периодом.
- [ ] **2.2.3.** Добавить `forbidden` (`uTorrent`, `AnyDesk`, `KMSAuto Net`) и `deprecated` (`pgAdmin 3`, `VirtualBox 6.1.16`, старые ветки `Node.js`).

### 2.3. Генерация оргструктуры, парка ПК и демонстрационных CSV-файлов
- [ ] **2.3.1.** Сгенерировать 50 сотрудников по подразделениям (*ПУ «СургутАСУнефть»*, *Бюро ИТ-решений в АСУТП*, *Бюро ИТ-решений в АСУПП*, *Отдел компетенции ИТ-решений*, *Бухгалтерия*, *Служба ИБ*), включая статусы `dismissed` и `role_changed`.
- [ ] **2.3.2.** Сгенерировать 60 рабочих станций (Windows 10/11 и Альт Рабочая Станция 10) и стартовый срез инсталляций + предзаполненный словарь популярных алиасов.
- [ ] **2.3.3.** Сформировать готовые демонстрационные файлы в `docs/demo_csv/` (в `utf-8` и `cp1251`) с «грязными» названиями процессов (`studio_visual_2022.exe`, `Google_Chrome_v2`, `chrome_setup.exe`, `dbeaver-ce-26.0-x64.exe`, `photoshop_2024_portable.exe`).
- [ ] **2.3.4.** Реализовать идемпотентную команду `make seed` в `Makefile`.

---

## Модуль 3. Аутентификация и защита коннектора (`app/core/security.py`, `app/routers/auth.py`)

### 3.1. JWT для веб-интерфейса и API-ключи для агентов
- [ ] **3.1.1.** Модель `User` (`users`) и предсозданные учётные записи в seed (`admin`, `director`, `secops`).
- [ ] **3.1.2.** Эндпоинты `POST /api/v1/auth/login` (выдача HS256 JWT) и `GET /api/v1/auth/me`.
- [ ] **3.1.3.** Зависимость `get_current_user` для защищённых операций изменения данных.
- [ ] **3.1.4.** Зависимость `verify_agent_api_key` (проверка заголовка `X-Agent-Key` через `secrets.compare_digest`) для приёма данных от агентов на `:8001`.

---

## Модуль 4. CRUD API справочников и ручного ведения учёта (`app/routers/`)

### 4.1. Лицензионные соглашения и договоры закупок (`/api/v1/licenses`, `/api/v1/contracts`)
- [ ] **4.1.1.** `GET /api/v1/licenses` — список с фильтрацией по `cost_category`, `license_type`, флагам рисков и поиском.
- [ ] **4.1.2.** `GET / POST / PUT / DELETE /api/v1/licenses/{id}` — просмотр и ведение карточек лицензий и текстов EULA.
- [ ] **4.1.3.** `GET / POST / PUT / DELETE /api/v1/contracts` — ведение закупленных квот лицензий, стоимости и сроков действия.

### 4.2. Каталог разрешённого ПО (`/api/v1/software`)
- [ ] **4.2.1.** `GET /api/v1/software` — пагинация и фильтры по `company_status` (`actual / deprecated / forbidden`), разделам/классам Минцифры, флагу `in_russian_registry`, типу лицензии и поисковой строке `q`.
- [ ] **4.2.2.** `GET /api/v1/software/classifiers` — дерево разделов и классов Реестра российского ПО для форм на фронтенде.
- [ ] **4.2.3.** `GET /api/v1/software/{id}` — полная карточка ПО: лицензии, квоты закупок, фактические установки, список хостов и синонимы процессов (`aliases`).
- [ ] **4.2.4.** `POST / PUT / DELETE /api/v1/software` — создание и редактирование ПО с автоматическим обновлением вектора `embedding`.

### 4.3. Сотрудники, хосты и ручной ввод установок (`/api/v1/employees`, `/api/v1/hosts`, `/api/v1/installations`)
- [ ] **4.3.1.** `GET / POST / PATCH /api/v1/employees` — ведение базы сотрудников (смена статуса на `dismissed` мгновенно подсвечивает закреплённые за ним платные лицензии как «зомби-софт»).
- [ ] **4.3.2.** `GET / POST / PATCH /api/v1/hosts` и `GET /api/v1/hosts/{id}` — список рабочих станций и детальный паспорт конкретного ПК со всеми процессами и рисками.
- [ ] **4.3.3.** `POST / DELETE /api/v1/installations` — ручное добавление/удаление факта установки ПО на выбранном компьютере (обязательное требование архитектуры со слайда 6).

---

## Модуль 5. Сервис сбора данных: CSV-импорт и Коннектор агентов (`ingest :8001`)

### 5.1. Отказоустойчивый CSV-импортёр (`app/services/csv_ingest.py`)
- [ ] **5.1.1.** Автоопределение кодировки: чтение `utf-8-sig` (BOM) с автоматическим фолбэком на `cp1251` (стандарт выгрузок из русского MS Excel на Windows).
- [ ] **5.1.2.** Автоопределение разделителя колонок (`,`, `;`, `\t`) через `csv.Sniffer`.
- [ ] **5.1.3.** Гибкий маппер заголовков столбцов (русские и английские синонимы: `hostname / имя_пк / компьютер`, `raw_name / process / software / наименование_по`, `version / версия`, `employee / фио / user`, `os / ос`, `last_used / последний_запуск`).
- [ ] **5.1.4.** Эндпоинт `POST /ingest/v1/csv`:
  - Валидация файла, расчёт SHA-256 и создание записи `ingest_batches`;
  - Идемпотентный батчевый upsert сотрудников, хостов и `installed_software`;
  - Мгновенный запуск быстрых ступеней мэтчинга (Exact + Normalized + Alias + Vector) и постановка пограничных записей в Celery для LLM-реранкинга;
  - Возврат подробного отчёта импорта (`total_rows`, `hosts_touched`, `matched_count`, `review_count`, `unmatched_count`, `new_critical_risks`).
- [ ] **5.1.5.** Эндпоинт `GET /ingest/v1/template.csv` для скачивания образца CSV-файла из UI.

### 5.2. Автоматизированный коннектор агентов (`POST /ingest/v1/agent/report`)
- [ ] **5.2.1.** Приём JSON-отчёта с конечного устройства (проверка `X-Agent-Key`, обновление `hosts.last_seen_at`, сверка списка установленного ПО и запущенных процессов).
- [ ] **5.2.2.** Эндпоинты статуса загрузок `GET /ingest/v1/batches` и `GET /ingest/v1/batches/{id}`.
- [ ] **5.2.3.** Реализация живого кроссплатформенного агента в `services/agent/example.py` (сбор реального установленного ПО/процессов на Windows и Linux и отправка на `/ingest/v1/agent/report` во время демонстрации).

---

## Модуль 6. Движок расчёта лицензий и Комплаенс-контроля (`app/services/compliance.py`) — **Ключевые 60% успеха**

### 6.1. Точный расчёт лицензионного баланса
- [ ] **6.1.1.** Дедупликация инсталляций при подсчёте `used_seats`:
  - Для `per_device` считать число **уникальных `host_id`** (чтобы `chrome.exe` и `chrome_proxy.exe` на одной рабочей станции считались за **1** занятое место, а не за 2);
  - Для `per_user` считать число **уникальных `employee_id`**.
- [ ] **6.1.2.** Расчёт `purchased_seats` по активным и действующим договорам (`is_active = true` и `valid_until >= CURRENT_DATE`), с поддержкой безлимита (`unlimited`) для разрешённого свободного ПО.
- [ ] **6.1.3.** Расчёт дефицита (`deficit = max(0, used_seats - purchased_seats)`), профицита (`surplus`) и денежной оценки штрафного риска (`deficit * unit_price_rub`).

### 6.2. Правила выявления 6 классов рисков (`RiskFinding`)
- [ ] **6.2.1.** **`LICENSE_DEFICIT` (`critical`)** — превышение числа инсталляций над купленными лицензиями (формат из ТЗ: *«Штрафной риск: MS Office установлен на 120 ПК при купленных 100 лицензиях»*).
- [ ] **6.2.2.** **`FORBIDDEN_SOFTWARE` (`critical`)** — обнаружение запрещённого к использованию ПО (`company_status == forbidden`).
- [ ] **6.2.3.** **`UNAPPROVED_SOFTWARE` (`high`)** — неразрешённое ПО (Shadow IT: программы на ПК, отсутствующие в каталоге разрешённого ПО).
- [ ] **6.2.4.** **`EULA_VIOLATION` (`high`)** — нарушение условий лицензии (`commercial_use_allowed == False` в корпоративной сети, сильный вирусный copyleft `AGPL`, истёкший `Trial` или договор).
- [ ] **6.2.5.** **`ZOMBIE_LICENSE` (`medium`)** — платные лицензии на ПК уволенных/переведённых сотрудников (`dismissed / role_changed`) или без запусков более `90` дней + расчёт суммы потенциальной экономии в рублях.
- [ ] **6.2.6.** **`DEPRECATED_SOFTWARE` (`medium`)** — устаревшее ПО (`company_status == deprecated` или версия ниже `min_allowed_version`).

### 6.3. Эндпоинты дашборда и экрана «Комплаенс-контроля» (`/api/v1/compliance`)
- [ ] **6.3.1.** `GET /api/v1/compliance/summary` — сводные KPI (процент комплаенса, штрафной риск в ₽, потенциал экономии на «зомби-софте» в ₽, количество критических нарушений, доля реестрового ПО РФ).
- [ ] **6.3.2.** `GET /api/v1/compliance/balance` — таблица баланса **«Куплено лицензий vs Установлено по факту»** по каждому продукту.
- [ ] **6.3.3.** `GET /api/v1/compliance/risks` — список всех выявленных рисков с фильтрами по типу, критичности и подразделению и списком затронутых ПК/сотрудников.
- [ ] **6.3.4.** `GET /api/v1/compliance/analytics` — данные для графиков (распределение по типам лицензий, классам Минцифры, топ отделов по рискам, структура использования платных лицензий).

---

## Модуль 7. AI-Модуль А: Smart Matching «грязных» имён процессов (`app/ai/matcher.py`)

### 7.1. Многоступенчатый пайплайн очистки и сопоставления
- [ ] **7.1.1.** **Ступень 1 — Нормализация строк:** очистка путей ОС, расширений (`.exe`, `.msi`), технических суффиксов (`_setup`, `x64`, `portable`, `repack`), разделителей `_`/`-` и извлечение версий/годов регулярными выражениями.
- [ ] **7.1.2.** **Ступень 2 — Поиск по эталону и словарю `software_aliases`:** мгновенное детерминированное сопоставление (`confidence = 1.0`) для уже известных процессов.
- [ ] **7.1.3.** **Ступень 3 — Векторный поиск (`pgvector`) + лексический фолбэк:** поиск Топ-5 ближайших позиций в `software_catalog` по косинусному сходству эмбеддингов (при недоступности сервиса эмбеддингов — автоматический фолбэк на токенный/триграммный скоринг).
- [ ] **7.1.4.** **Ступень 4 — Фоновый LLM Reranker в Celery (`app/worker.py`):** батчевая классификация неоднозначных имён процессов (например, `studio_visual_2022.exe` → `Microsoft Visual Studio 2022`) со строгим JSON-ответом `{software_id, confidence, reasoning}`.
- [ ] **7.1.5.** Разделение результатов по порогам: `>= 0.85` → `matched`, `0.55..0.85` → `needs_review` (рекомендация оператору), `< 0.55` → `unmatched`.

### 7.2. Интерфейс подтверждения (Human-in-the-Loop) и песочница
- [ ] **7.2.1.** `GET /api/v1/matching/queue` — очередь нераспознанных и ожидающих проверки процессов с подсказками ИИ.
- [ ] **7.2.2.** `POST /api/v1/matching/{installation_id}/resolve` — подтверждение или ручная привязка процесса с **автоматическим сохранением правила в `software_aliases`** и пересчётом всех аналогичных записей на других ПК.
- [ ] **7.2.3.** `POST /api/v1/matching/demo-test` — интерактивная проверка любой «грязной» строки в реальном времени для демонстрации жюри.

---

## Модуль 8. AI-Модуль Б: Анализатор лицензионных соглашений EULA (`app/ai/eula_parser.py`)

### 8.1. Обработка текстов и файлов лицензий
- [ ] **8.1.1.** Приём сырого текста EULA или загрузка `.txt` / `.pdf` с извлечением текста и умной разбивкой длинных документов по ключевым юридическим секциям.

### 8.2. Извлечение юридических правил и скрытых рисков
- [ ] **8.2.1.** Запрос к LLM со строгой схемой ответа `EulaAnalysisResult`:
  - разрешение коммерческого использования в корпоративной среде (`yes / no / restricted`) + точная цитата;
  - наличие скрытых подписок / автопродления / платных опций;
  - copyleft-риск раскрытия исходного кода (`GPL / AGPL`);
  - риск передачи телеметрии и данных за пределы контура компании;
  - итоговый уровень риска и краткая памятка на русском языке (3–5 пунктов).
- [ ] **8.2.2.** Детерминированный эвристический фолбэк по ключевым юридическим формулировкам на случай таймаута внешнего ИИ.
- [ ] **8.2.3.** Эндпоинты `POST /api/v1/ai/eula/analyze` (интерактивная проверка любого текста) и `POST /api/v1/licenses/{id}/analyze` (сохранение разбора в карточку лицензии с обновлением комплаенса).

---

## Модуль 9. AI-Модуль В: Чат-ассистент ИТ-директора (`app/ai/assistant.py`)

### 9.1. Гибридный аналитический движок (Tool Calling + Безопасный Text-to-SQL)
- [ ] **9.1.1.** Набор проверенных аналитических инструментов (Tools) поверх `Compliance Engine` для 100%-ной точности цифр по типовым вопросам:
  - поиск нелицензионных установок конкретного продукта (*«У кого стоит нелицензионный Photoshop?»*);
  - анализ простаивающих и «зомби»-лицензий (*«Сколько лицензий простаивает?»*);
  - сводка по запрещённому ПО, Shadow IT и финансовым рискам по отделам.
- [ ] **9.1.2.** Безопасный Text-to-SQL для произвольных вопросов по базе:
  - генерация `SELECT` только по разрешённым таблицам и аналитическим `VIEW` (`v_software_compliance`, `v_host_risks`);
  - строгий статический фильтр SQL (запрет `;`, комментариев, любых DML/DDL-команд, системных каталогов и таблицы `users`, принудительный `LIMIT 100`);
  - выполнение исключительно через `ReadOnlySessionLocal` с `statement_timeout = 3s`.

### 9.2. Эндпоинты чата (`/api/v1/ai/chat`)
- [ ] **9.2.1.** `POST /api/v1/ai/chat` — возвращает текстовый аналитический вывод в Markdown + опциональную структурированную таблицу (`columns`, `rows`) для красивой отрисовки в чате.
- [ ] **9.2.2.** `GET /api/v1/ai/chat/suggestions` — список быстрых демонстрационных вопросов для защиты проекта.

---

## Модуль 10. Тестирование, метрики и готовность к защите в VK Cloud

### 10.1. Автоматические тесты (`tests/`)
- [ ] **10.1.1.** Сохранение 100% прохождения `tests/test_scaffold.py` и `ruff check`.
- [ ] **10.1.2.** `tests/test_compliance.py` — юнит- и интеграционные тесты расчёта дефицита (`120 vs 100`), дедупликации нескольких процессов одного ПО на одном хосте, выявления «зомби-софта» и `forbidden` ПО.
- [ ] **10.1.3.** `tests/test_csv_ingest.py` — тесты загрузки CSV в кодировках `utf-8` и `cp1251`, с разделителями `,` и `;`, и идемпотентности повторного импорта.
- [ ] **10.1.4.** `tests/test_sql_guard.py` — негативные тесты безопасности SQL-валидатора Чат-ассистента.

### 10.2. Эксплуатационная надёжность на демо
- [ ] **10.2.1.** Экспорт реальных бизнес-метрик Prometheus в `/metrics` (`sam_hosts_total`, `sam_compliance_deficit_seats`, `sam_financial_risk_rub`, `sam_zombie_licenses_total`).
- [ ] **10.2.2.** Проверка режима **Graceful Degradation**: при отключённом или медленном LLM весь MVP, импорт CSV и базовые фолбэки продолжают работать без ошибок `500`.
- [ ] **10.2.3.** Сервисный эндпоинт `POST /api/v1/admin/reset-demo` — мгновенный возврат демо-базы к эталонному состоянию перед выступлением перед жюри.

---

## Рекомендуемый порядок спринтов

1. **Спринт 1 (Старт, часы 1–3):** Модуль 0 → Модуль 1 → Модуль 2 (`make migrate` + `make seed`). Разблокирует фронтенд (живой Swagger + наполненная БД) и первый деплой в VK Cloud.
2. **Спринт 2 (Ядро расчётов, часы 4–8):** Модуль 6 (Compliance Engine) → Модуль 4 (CRUD справочников) → Модуль 3 (Auth). Оживает главный экран «Комплаенс-контроля».
3. **Спринт 3 (Сбор данных, часы 9–12):** Модуль 5 (CSV-импорт с `cp1251` + Коннектор и скрипт агента). Полностью закрывает обязательный MVP (60% итоговой оценки).
4. **Спринт 4 (AI-Upgrade, часы 13–20):** Модуль 7 (Smart Matching) → Модуль 8 (Парсер EULA) → Модуль 9 (Чат-ассистент ИТ-директора).
5. **Спринт 5 (Стабилизация и питч, последние 4 часа):** Модуль 10 (автотесты, проверка фолбэков без интернета/LLM, `reset-demo`, финальный прогон демо-сценария).
