# Frontend ↔ Backend Audit Report

**Дата:** 2026-07-08  
**Версия:** 1.0  
**Проект:** GraphRAG Platform  
**Проверяемые компоненты:** [`frontend/js/app.js`](frontend/js/app.js), [`frontend/js/api.js`](frontend/js/api.js), [`frontend/index.html`](frontend/index.html), [`frontend/css/styles.css`](frontend/css/styles.css) + все endpoint'ы бэкенда

---

## 1. Фронтенд: Баги и проблемы

### 1.1 XSS-уязвимости (критические)

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|--------------|
| [`app.js`](frontend/js/app.js:133) | 133–137 | `toast()` использует `innerHTML` для вставки пользовательского сообщения `m` без экранирования. Вредоносный HTML (например, `<img onerror="...">`) может быть выполнен | 🔴 Критический | Заменить `innerHTML` на `textContent` или экранировать через `escapeHtml()` |
| [`app.js`](frontend/js/app.js:527) | 527–548 | В таблице отделов (`loadDeptTable`) значения `d.name`, `d.code`, `d.description` вставляются через `innerHTML` без экранирования | 🔴 Критический | Использовать `textContent` или экранирование через `escapeHtml()` |
| [`app.js`](frontend/js/app.js:1291) | 1291–1334 | В таблице документов (`loadDocs`) значения `doc.title`, `doc.id` и др. вставляются через `innerHTML` | 🔴 Критический | Использовать `textContent` или экранирование через `escapeHtml()` |
| [`app.js`](frontend/js/app.js:624) | 624–634 | `marked.parse(text)` без опции `sanitize` — при загрузке с CDN marked@v4+ по умолчанию разрешает HTML. Ответ ассистента может содержать опасные теги | 🔴 Критический | Использовать `DOMPurify.sanitize()` на выходе `marked.parse()`, или экранировать HTML перед `renderMd` |

### 1.2 Логические ошибки и баги

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|--------------|
| [`app.js`](frontend/js/app.js:209) | 209–227 | Функция `pollPhase()` определена, но **никогда не вызывается** (dead code). Везде используется `poll()` | 🟡 Средний | Удалить мёртвый код |
| [`api.js`](frontend/js/api.js:100) | 100 | Метод `api.runTests()` определён, но **не используется** — вместо него в `app.js:1631` используется raw `fetch` | 🟡 Средний | Либо использовать `api.runTests()`, либо удалить метод |
| [`app.js`](frontend/js/app.js:1267) | 1267 | Для запроса списка документов используется raw `fetch` напрямую вместо метода API. Несоответствие стилю кода | 🟡 Средний | Вынести в `api.getDocuments()` для единообразия |
| [`app.js`](frontend/js/app.js:1371) | 1371 | Для удаления документа используется raw `fetch` вместо вызова `api.del()` | 🟡 Средний | Использовать `api.del(`${API_B}/graph/document/${id}`)` или добавить метод в `GraphRAGApi` |
| [`app.js`](frontend/js/app.js:297) | 297–315 | `modal()` каждый раз добавляет новый `onclick` обработчик на `#modal-overlay`. При многократном вызове обработчики накапливаются — утечка памяти | 🟡 Средний | Удалять старый обработчик перед добавлением нового, либо использовать `addEventListener`/`removeEventListener` |

### 1.3 Проблемы с API-интеграцией

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|--------------|
| [`app.js`](frontend/js/app.js:1631) | 1631 | Ручное формирование `Authorization` хедера: `Bearer ${api.token}`. Дублирует логику из `api.headers` | 🟡 Средний | Использовать `headers: api.headers` как везде |
| [`app.js`](frontend/js/app.js:1446) | 1446 | `api.getUsers(Object.fromEntries(q))` — избыточное преобразование `URLSearchParams → Object → URLSearchParams` | 🟢 Низкий | Упростить: `api.getUsers(Object.fromEntries(q))` → `api.getUsers(params)` |
| [`api.js`](frontend/js/api.js:68) | 68–70 | `api.getUsers()` не обрабатывает 401/403 отдельно от прочих ошибок | 🟡 Средний | Добавить проверку статуса 401 → `clearToken()` |
| [`app.js`](frontend/js/app.js:1253) | 1253–1256 | Жёстко закодированный `page_size: 15`, в то время как на бэкенде дефолтный `page_size=20` (см. [`graph.py`](backend/app/api/v1/graph.py:117)) | 🟢 Низкий | Синхронизировать константы page_size |

### 1.4 Отсутствие обработки ошибок / retry-логики

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|--------------|
| [`api.js`](frontend/js/api.js:24) | 24–46 | HTTP-helper'ы (`get`, `post`, `put`, `del`) не имеют retry-логики при временных сетевых ошибках | 🟡 Средний | Добавить retry (1-2 попытки) для идемпотентных GET-запросов |
| [`app.js`](frontend/js/app.js:361) | 361 | После успешного логина нет проверки, что `getMe()` вернул пользователя с `is_active=true` | 🟢 Низкий | Проверить `u.is_active` после логина |

### 1.5 Code Smells

| Файл | Строка | Проблема | Уровень | Рекомендация |
|------|--------|----------|---------|--------------|
| [`api.js`](frontend/js/api.js:5) | 5 | `API_BASE` — magic string, дублирующая логику из `app.js:15` | 🟢 Низкий | Использовать единую константу (экспорт из api.js) |
| [`app.js`](frontend/js/app.js:133) | 133–137 | `innerHTML` для тостов — помимо XSS, это code smell: смешивание разметки и логики | 🟡 Средний | Использовать `document.createElement()` как в `addMsg()` |
| [`app.js`](frontend/js/app.js:15) | 15–17 | Magic string `http://localhost:8000/api/v1` и `/api/v1` дублируются в `api.js:5` | 🟢 Низкий | Вынести в единый конфиг |

---

## 2. Сравнение эндпоинтов

### 2.1 Эндпоинты бэкенда — статус использования фронтом

| Эндпоинт (бэк) | Метод | Используется фронтом? | URL во фронте | Статус |
|----------------|-------|-----------------------|---------------|--------|
| `/health` | GET | ❌ Не используется | — | Мёртвый код |
| `/config/services` | GET | ✅ Да | `/api/v1/config/services` | ✅ |
| `/auth/register` | POST | ✅ Да | `/api/v1/auth/register` | ✅ |
| `/auth/login` | POST | ✅ Да | `/api/v1/auth/login` | ✅ |
| `/auth/me` | GET | ✅ Да | `/api/v1/auth/me` | ✅ |
| `/auth/sessions` | POST | ❌ Не используется | — | Мёртвый код |
| `/auth/sessions` | GET | ❌ Не используется | — | Мёртвый код |
| `/auth/users` | GET | ✅ Да | `/api/v1/auth/users?...` | ✅ |
| `/auth/users/{user_id}` | PUT | ✅ Да | `/api/v1/auth/users/${uid}` | ✅ |
| `/auth/users/{user_id}` | DELETE | ✅ Да | `/api/v1/auth/users/${uid}` | ✅ |
| `/auth/users/{user_id}/impersonate` | POST | ✅ Да | `/api/v1/auth/users/${uid}/impersonate` | ✅ |
| `/chat` | POST | ✅ Да | `/api/v1/chat` | ✅ |
| `/chat/stream` | POST | ❌ Не используется | — | Мёртвый код |
| `/chat/history` | GET | ✅ Да | `/api/v1/chat/history?limit=...` | ✅ |
| `/chat/history` | DELETE | ✅ Да | `/api/v1/chat/history` | ✅ |
| `/ingest/status/{doc_id}` | GET | ✅ Да | `/api/v1/ingest/status/${did}` | ✅ |
| `/ingest` | POST | ✅ Да | `/api/v1/ingest` | ✅ |
| `/ingest/file` | POST | ✅ Да | `/api/v1/ingest/file` | ✅ |
| `/ingest/url` | POST | ✅ Да | `/api/v1/ingest/url` | ✅ |
| `/graph/visualize` | GET | ❌ Не используется | — | Мёртвый код |
| `/graph/search` | POST | ❌ Не используется | — | Мёртвый код |
| `/graph/entity/{entity_name}` | GET | ❌ Не используется | — | Мёртвый код |
| `/graph/stats` | GET | ✅ Да | `/api/v1/graph/stats` | ✅ |
| `/graph/clear` | DELETE | ✅ Да | `/api/v1/graph/clear` | ✅ |
| `/graph/documents` | GET | ✅ Да | `/api/v1/graph/documents?...` | ✅ |
| `/graph/document/{doc_id}/content` | GET | ✅ Да | `/api/v1/graph/document/${docId}/content` | ✅ |
| `/graph/document/{doc_id}` | PUT | ✅ Да | `/api/v1/graph/document/${docId}` | ✅ |
| `/graph/document/{doc_id}` | DELETE | ✅ Да | `/api/v1/graph/document/${id}` (DELETE) | ✅ |
| `/tests/run` | POST | ✅ Да | `/api/v1/tests/run` (через fetch) | ✅ |
| `/departments/` | GET | ✅ Да | `/api/v1/departments/` | ✅ |
| `/departments/` | POST | ✅ Да | `/api/v1/departments/` | ✅ |
| `/departments/{dep_id}` | PUT | ✅ Да | `/api/v1/departments/${id}` | ✅ |
| `/departments/{dep_id}` | DELETE | ✅ Да | `/api/v1/departments/${id}` | ✅ |
| `/admin/settings` | GET | ✅ Да | `/api/v1/admin/settings` | ✅ |
| `/admin/settings/{setting_id}` | PUT | ✅ Да | `/api/v1/admin/settings/${id}` | ✅ |
| `/admin/settings/category/{category}` | PUT | ✅ Да | `/api/v1/admin/settings/category/${category}` | ✅ |
| `/admin/_debug/registry` | GET | ❌ Не используется | — | Отладка |
| `/admin/settings/reload` | POST | ✅ Да | `/api/v1/admin/settings/reload` | ✅ |
| `/admin/settings/history` | GET | ✅ Да | `/api/v1/admin/settings/history?limit=...` | ✅ |
| `/admin/settings/{category}` | GET | ✅ Да | `/api/v1/admin/settings/${category}` | ✅ |

**Итого мёртвых эндпоинтов:** **8 шт.**  
( `/health`, `POST /auth/sessions`, `GET /auth/sessions`, `POST /chat/stream`, `GET /graph/visualize`, `POST /graph/search`, `GET /graph/entity/{entity_name}`, `GET /admin/_debug/registry` )

### 2.2 Запросы фронта — сверка с бэкендом

| Запрос (фронт) | URL | Эндпоинт существует? | Статус |
|----------------|-----|---------------------|--------|
| `api.login()` | `POST /auth/login` | ✅ Да | ✅ |
| `api.register()` | `POST /auth/register` | ✅ Да | ✅ |
| `api.getMe()` | `GET /auth/me` | ✅ Да | ✅ |
| `api.getUsers()` | `GET /auth/users?...` | ✅ Да | ✅ |
| `api.updateUser()` | `PUT /auth/users/{uid}` | ✅ Да | ✅ |
| `api.deleteUser()` | `DELETE /auth/users/{uid}` | ✅ Да | ✅ |
| `api.impersonate()` | `POST /auth/users/{uid}/impersonate` | ✅ Да | ✅ |
| `api.sendMessage()` | `POST /chat` | ✅ Да | ✅ |
| `api.getChatHistory()` | `GET /chat/history?...` | ✅ Да | ✅ |
| `api.clearChatHistory()` | `DELETE /chat/history` | ✅ Да | ✅ |
| `api.getIngestStatus()` | `GET /ingest/status/{did}` | ✅ Да | ✅ |
| `api.ingestText()` | `POST /ingest` | ✅ Да | ✅ |
| `api.ingestFile()` | `POST /ingest/file` | ✅ Да | ✅ |
| `api.ingestUrl()` | `POST /ingest/url` | ✅ Да | ✅ |
| `api.getGraphStats()` | `GET /graph/stats` | ✅ Да | ✅ |
| `api.clearGraphData()` | `DELETE /graph/clear` | ✅ Да | ✅ |
| `api.updateDocument()` | `PUT /graph/document/{docId}` | ✅ Да | ✅ |
| `api.getServiceConfig()` | `GET /config/services` | ✅ Да | ✅ |
| `api.getDepartments()` | `GET /departments/` | ✅ Да | ✅ |
| `api.createDepartment()` | `POST /departments/` | ✅ Да | ✅ |
| `api.updateDepartment()` | `PUT /departments/{id}` | ✅ Да | ✅ |
| `api.deleteDepartment()` | `DELETE /departments/{id}` | ✅ Да | ✅ |
| `fetch(...)` в `loadDocs()` | `GET /graph/documents?...` | ✅ Да | ✅ |
| `fetch(...)` в `downloadDoc()` | `GET /graph/document/{docId}/content` | ✅ Да | ✅ |
| `fetch(...)` в удалении документа | `DELETE /graph/document/{id}` | ✅ Да | ✅ |
| `fetch(...)` в `runTests` | `POST /tests/run` | ✅ Да | ✅ |
| `AdminAPI.getAllSettings()` | `GET /admin/settings` | ✅ Да | ✅ |
| `AdminAPI.getCategorySettings()` | `GET /admin/settings/{category}` | ✅ Да | ✅ |
| `AdminAPI.updateSetting()` | `PUT /admin/settings/{id}` | ✅ Да | ✅ |
| `AdminAPI.updateCategory()` | `PUT /admin/settings/category/{category}` | ✅ Да | ✅ |
| `AdminAPI.reloadSettings()` | `POST /admin/settings/reload` | ✅ Да | ✅ |
| `AdminAPI.getHistory()` | `GET /admin/settings/history?...` | ✅ Да | ✅ |

**Итого отсутствующих эндпоинтов:** **0 шт.** — все URL фронта корректны.

---

## 3. Сравнение DTO / типов данных

### 3.1 User (авторизация / управление пользователями)

| Схема (бэк) | Поле | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|-------------|------|-----------|-------------|-----------|-----------|
| `UserResponse` | `id` | `int` | `number` | ✅ | |
| `UserResponse` | `email` | `str` | `string` | ✅ | |
| `UserResponse` | `username` | `Optional[str]` | `string` | ✅ | Фронт выводит `u.username \|\| '—'` |
| `UserResponse` | `role` | `str` | `string` | ✅ | |
| `UserResponse` | `department` | `str` | `string` | ✅ | |
| `UserResponse` | `created_at` | `datetime` | `string` | ✅ | Не используется напрямую |
| — | `clearance_level` | ❌ **НЕТ в схеме** | `number` (ожидает) | ❌ Отсутствует | `get_me()` возвращает `UserResponse` без `clearance_level`, но [`app.js`](frontend/js/app.js:1484) ожидает `u.clearance_level` для списка пользователей (через `getUsers()`) |
| — | `is_active` | ❌ **НЕТ в схеме** | `boolean` (ожидает) | ❌ Отсутствует | `list_users()` возвращает объекты ORM, где `is_active` есть, но `UserResponse` его не декларирует |

### 3.2 Chat

| Схема (бэк) | Поле | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|-------------|------|-----------|-------------|-----------|-----------|
| `ChatResponse` | `messages` | `List[Message]` | `array` | ✅ | |
| `ChatResponse` | `sources` | `List[dict]` | `array` | ✅ | |
| `Message` | `role` | `Literal["user","assistant","system"]` | `string` | ✅ | |
| `Message` | `content` | `str` | `string` | ✅ | |
| `GET /chat/history` | `messages[].sources` | `Optional[dict]` (JSON) | `object\|null` | ✅ | Фронт использует `m.sources` |

### 3.3 Ingestion

| Схема (бэк) | Поле | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|-------------|------|-----------|-------------|-----------|-----------|
| `IngestStatusResponse` | `document_id` | `str` | `string` | ✅ | |
| `IngestStatusResponse` | `status` | `str` | `string` | ✅ | Фронт проверяет `completed`, `failed`, `processing` |
| `IngestStatusResponse` | `step_name` | `str` | `string` | ✅ | |
| `IngestStatusResponse` | `error` | `Optional[str]` | `string\|null` | ✅ | |
| `IngestRequest` | `content` | `Optional[str]` | `string` | ✅ | |

### 3.4 Документы

| Поле (бэк `/graph/documents`) | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|-------------------------------|-----------|-------------|-----------|-----------|
| `id` | `str` | `string` | ✅ | |
| `title` | `str` | `string` | ✅ | |
| `clearance_level` | `int` | `number` | ✅ | Ключ в ответе бэка — `clearance_level` |
| `department` | `str` | `string` | ✅ | |
| `chunks` | `int` | `number` | ✅ | |
| `created_at` | `str (isoformat)` | `string` | ✅ | Парсится через `new Date()` |

### 3.5 Graph Stats

| Поле (бэк) | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|------------|-----------|-------------|-----------|-----------|
| `graph.node_count` | `int` | `number` | ✅ | |
| `graph.edge_count` | `int` | `number` | ✅ | |
| `graph.documents` | `int` | `number` | ✅ | |
| `graph.entities` | `int` | `number` | ✅ | |

### 3.6 Departments

| Схема (бэк) | Поле | Тип (бэк) | Тип (фронт) | Совпадает? | Примечание |
|-------------|------|-----------|-------------|-----------|-----------|
| `DepartmentResponse` | `id` | `int` | `number` | ✅ | |
| `DepartmentResponse` | `name` | `str` | `string` | ✅ | |
| `DepartmentResponse` | `code` | `str` | `string` | ✅ | |
| `DepartmentResponse` | `description` | `Optional[str]` | `string` | ✅ | |

**Итого DTO-расхождений:** **1 существенное**:  
- [`UserResponse`](backend/app/models/schemas.py:62) не содержит `clearance_level` и `is_active`, хотя фронт ожидает эти поля (особенно для `getUsers()`)

---

## 4. Анализ авторизации

### 4.1 Как передаётся токен

- **Фронтенд:** Токен JWT хранится в `localStorage` под ключом `graphrag_token`
- **Заголовок:** `Authorization: Bearer ${this.token}` — см. [`api.js:18`](frontend/js/api.js:18)
- **Бэкенд:** Ожидает заголовок `Authorization: Bearer <token>` через `HTTPBearer()` — см. [`auth.py:23`](backend/app/api/v1/auth.py:23)
- **Совпадение:** ✅ Полное совпадение схемы заголовка

### 4.2 Управление токеном

| Сценарий | Фронтенд | Бэкенд | Статус |
|----------|----------|--------|--------|
| Логин | `api.login()` → `setToken(d.access_token)` | `POST /login` → возвращает `TokenResponse` с `access_token` | ✅ |
| Регистрация | `api.register()` → тост об успехе | `POST /register` → возвращает `UserResponse` (без токена) | ✅ |
| Истечение токена | `api.getMe()` → `if (!r.ok) { this.clearToken() }` | 401 при невалидном токене | ✅ |
| 401 в других запросах | Выбрасывается ошибка, показывается тост | Бэкенд возвращает 401 | ❌ Нет автоматического редиректа на логин |
| Impersonate | Сохраняет исходный токен в `adminToken`, переключается на целевой | `POST /users/{id}/impersonate` → возвращает новый токен | ✅ |
| Выход из impersonate | `api.restoreAdminToken()` восстанавливает исходный токен | — | ✅ |

### 4.3 Обработка 401/403

- **Фронтенд:** Нет **глобального** перехватчика HTTP-статусов 401/403. Если токен истекает во время сессии, пользователь увидит тост с ошибкой, но **не будет перенаправлен на экран логина**. Это может привести к состоянию, когда пользователь думает, что система работает, но все запросы падают с ошибкой.
- **Бэкенд:** Возвращает 401 для недействительных токенов, 403 для недостаточных прав.
- **Рекомендация:** Добавить глобальный interceptor (через обёртку `fetch`), который при 401 очищает токен и перенаправляет на `#login`.

---

## 5. Итоговые выводы

### Сводка

| Метрика | Значение |
|---------|----------|
| **Эндпоинтов бэкенда всего** | 40 |
| **Используется фронтом** | 32 (80%) |
| **Не используется (мёртвый код)** | 8 (20%) |
| **Эндпоинтов, запрашиваемых фронтом, не найденных на бэке** | 0 |
| **DTO-расхождений** | 1 (отсутствие `clearance_level`/`is_active` в `UserResponse`) |
| **Критических проблем фронта** | 4 (XSS в toast, таблицах отделов, документов и в marked) |
| **Проблем среднего уровня** | 8 |
| **Проблем низкого уровня** | 5 |

### Критические проблемы (требуют немедленного исправления)

1. **XSS в [`toast()`](frontend/js/app.js:133)** — использование `innerHTML` с непроверенным пользовательским вводом. Позволяет выполнить произвольный JS при отображении сообщения об ошибке.
2. **XSS в таблице отделов** — [`loadDeptTable()`](frontend/js/app.js:527) вставляет `d.name`, `d.code`, `d.description` через `innerHTML`.
3. **XSS в таблице документов** — [`loadDocs()`](frontend/js/app.js:1291) вставляет `doc.title`, `doc.id` через `innerHTML`.
4. **XSS через `marked.parse()`** — [`renderMd()`](frontend/js/app.js:624) не санитизирует вывод. Ответ ассистента может содержать XSS.

### Важные проблемы среднего уровня

5. **Нет глобального обработчика 401** — пользователь не перенаправляется на логин при истечении токена
6. **Мёртвый код:** [`pollPhase()`](frontend/js/app.js:209), [`api.runTests()`](frontend/js/api.js:100), 8 эндпоинтов бэкенда
7. **Несоответствие `UserResponse`:** отсутствуют поля `clearance_level` и `is_active`, ожидаемые фронтом
8. **Утечка обработчиков** в [`modal()`](frontend/js/app.js:297) при многократном вызове

### Рекомендации

1. **Первоочередные:** Исправить 4 XSS-уязвимости (заменить `innerHTML` на безопасные методы)
2. **Добавить глобальный HTTP-интерсептор** для обработки 401 → редирект на логин
3. **Синхронизировать DTO:** добавить `clearance_level` и `is_active` в `UserResponse`
4. **Очистить мёртвый код:** удалить неиспользуемые функции и эндпоинты
5. **Устранить дублирование:** вынести `API_BASE` в единый модуль, использовать `api.headers` везде
6. **Добавить единый page_size** как константу, используемую и фронтом, и бэком

---

*Report generated by automated audit tool.*
