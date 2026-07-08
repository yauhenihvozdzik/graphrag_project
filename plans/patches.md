# План исправлений GraphRAG Platform

**Дата:** 2026-07-08
**Основание:** Три аудита — архитектурный, бэкенд-код, фронтенд-бэкенд
**Всего проблем:** 11 CRITICAL · 8 HIGH · 14 MEDIUM · 9 LOW

---

## 🔴 CRITICAL — Немедленное исправление

### 1. Эндпоинт `/config/services` — утечка паролей инфраструктуры

**Файл:** [`backend/app/api/v1/api.py:73-168`](../backend/app/api/v1/api.py:73)

**Проблема:** Эндпоинт без аутентификации возвращает пароли Neo4j, MinIO, Grafana, pgAdmin, PostgreSQL в открытом виде. Любой, кто имеет доступ к сети, может получить доступ ко всей инфраструктуре.

**Решение:** Замаскировать пароли и секреты, оставив URL для browser-доступа без credentials.

**Патч:**

```diff
--- a/backend/app/api/v1/api.py
+++ b/backend/app/api/v1/api.py
@@ -96,26 +96,21 @@
     def _auto_login(url: str, user: str, pw: str) -> str:
         """Embed credentials into URL for auto-login."""
         import re
         return re.sub(r"(https?://)(.+)", rf"\1{user}:{pw}@\2", url)
 
     neo4j_browser = _browser_url(7474, "/browser/")
 
     return {
         "success": True,
         "services": {
             "neo4j": {
                 "label": "Neo4j Browser",
                 "description": "Графовая СУБД",
                 "browser_url": neo4j_browser,
-                "auto_login_url": _auto_login(neo4j_browser, settings.NEO4J_USER, settings.NEO4J_PASSWORD),
-                "user": settings.NEO4J_USER,
-                "password": settings.NEO4J_PASSWORD,
             },
             "minio": {
                 "label": "MinIO Console",
                 "description": "S3-хранилище документов",
                 "browser_url": _browser_url(9001),
-                "user": settings.S3_ACCESS_KEY,
-                "password": settings.S3_SECRET_KEY,
             },
             "qdrant": {
                 "label": "Qdrant Dashboard",
@@ -131,28 +126,14 @@
             "grafana": {
                 "label": "Grafana",
                 "description": "Метрики и дашборды",
                 "browser_url": _browser_url(3001),
-                "user": "admin",
-                "password": "graphrag_admin",
             },
             "prometheus": {
                 "label": "Prometheus",
                 "description": "Сбор метрик",
                 "browser_url": _browser_url(9090),
             },
             "pgadmin": {
                 "label": "pgAdmin",
                 "description": "Управление PostgreSQL",
                 "browser_url": _browser_url(5050),
-                "user": "admin@graphrag.com",
-                "password": "pgadmin",
-                "db_user": "postgres",
-                "db_password": "postgres",
             },
         },
     }
```

**Дополнительно:** Удалить функцию `_auto_login()` — она больше не используется.

**Риски:** 
- Фронтенд использует этот эндпоинт для отображения browser URL. После патча `auto_login_url` пропадёт — нужно убедиться, что фронт не падает при отсутствии поля.
- Если какая-то интеграция полагается на `password` поле — сломается. Проверить usage в frontend.

---

### 2. Cypher Injection — параметризация запросов

#### 2a. RBAC filter — f-строка с department

**Файл:** [`backend/app/core/security/rbac.py:146-164`](../backend/app/core/security/rbac.py:146)

**Проблема:** Метод `build_cypher_filter()` возвращает строку WHERE с вставкой `context.department` через f-строку. Пользователь с department `' OR 1=1 --` получит полный доступ к графу.

**Решение:** Изменить сигнатуру `build_cypher_filter()` на возврат кортежа `(where_clause: str, params: dict)`, чтобы параметризовать значение department.

**Патч:**

```diff
--- a/backend/app/core/security/rbac.py
+++ b/backend/app/core/security/rbac.py
@@ -146,20 +146,22 @@
 
-    def build_cypher_filter(self, context: AccessContext) -> str:
+    def build_cypher_filter(self, context: AccessContext) -> tuple[str, dict]:
         """Generate a Cypher WHERE clause for Neo4j queries with RBAC filtering."""
         if context.role == Role.ADMIN:
-            return ""
+            return "", {}
 
         conditions = []
+        params = {}
 
         # Clearance filter
         conditions.append(
             f"(n.clearance_level IS NULL OR n.clearance_level <= {context.clearance.value})"
         )
 
         # Department filter
         if context.department != "all":
             conditions.append(
-                f"(n.department IS NULL OR n.department = 'all' OR n.department = '{context.department}')"
+                "(n.department IS NULL OR n.department = 'all' OR n.department = $rbac_department)"
             )
+            params["rbac_department"] = context.department
 
-        return " AND ".join(conditions)
+        return " AND ".join(conditions), params
```

**Необходимо обновить все места вызова `build_cypher_filter()`:**

1. [`graph.py:43`](../backend/app/api/v1/graph.py:43) — `rbac_filter = rbac_service.build_cypher_filter(access_context)` → `rbac_filter, rbac_params = ...`
2. [`graph.py:58`](../backend/app/api/v1/graph.py:58) — аналогично
3. [`graph.py:67`](../backend/app/api/v1/graph.py:67) — аналогично
4. [`neo4j_service.py:96`](../backend/app/services/neo4j_service.py:96) — передавать `rbac_params` в `s.run()`
5. [`neo4j_service.py:114`](../backend/app/services/neo4j_service.py:114) — аналогично
6. [`neo4j_service.py:130`](../backend/app/services/neo4j_service.py:130) — аналогично
7. [`neo4j_service.py:135`](../backend/app/services/neo4j_service.py:135) — аналогично
8. [`neo4j_service.py:148`](../backend/app/services/neo4j_service.py:148) — аналогично

**Риски:** 
- Рефакторинг затрагивает много файлов. Важно проверить каждый вызов.
- Старый код передавал filter как строку, которую вставляли в f-строку запроса. Новый код должен передавать params в `s.run()`.

#### 2b. Relationship type — небезопасная вставка

**Файл:** [`backend/app/services/neo4j_service.py:62-63`](../backend/app/services/neo4j_service.py:62)

**Проблема:** `rel_type` проходит через `.upper().replace(" ","_").replace("-","_")`, что не защищает от спецсимволов Cypher.

**Решение:** Использовать строгий regex для валидации `rel_type`:

```diff
--- a/backend/app/services/neo4j_service.py
+++ b/backend/app/services/neo4j_service.py
@@ -1,3 +1,4 @@
+import re
 from contextlib import asynccontextmanager
 from typing import Any, AsyncGenerator, Optional
 
@@ -59,7 +60,8 @@
 
     async def create_relationship(self, source_id: str, target_id: str, rel_type: str, properties: Optional[dict] = None) -> dict:
-        props = properties or {}; safe = rel_type.upper().replace(" ","_").replace("-","_")
+        props = properties or {}
+        safe = re.sub(r"[^A-Z0-9_]", "_", rel_type.upper())
+        safe = safe.strip("_") or "RELATED_TO"
         q = f"MATCH (s:Entity {{id:$source_id}}) MATCH (t:Entity {{id:$target_id}}) MERGE (s)-[r:{safe}]->(t) SET r+=$properties, r.updated_at=datetime() RETURN type(r) AS rel_type, r{{.*}} AS properties"
```

**Риски:** 
- Если оригинальный rel_type содержал только недопустимые символы, `safe` станет пустым. Нужен fallback `"RELATED_TO"`.
- Не меняет поведение для корректных rel_type.

---

### 3. Mass Assignment — Pydantic-схемы вместо `dict`

#### 3a. PUT /users/{user_id}

**Файл:** [`backend/app/api/v1/auth.py:153-154`](../backend/app/api/v1/auth.py:153)

**Проблема:** `updates: dict` позволяет администратору установить любые поля, включая потенциально опасные.

**Решение:** Создать Pydantic-схему в [`schemas.py`](../backend/app/models/schemas.py) и использовать её:

```diff
--- a/backend/app/models/schemas.py
+++ b/backend/app/models/schemas.py
@@ -69,6 +69,16 @@
 class UserResponse(BaseResponse):
     id: int
     email: str
     username: Optional[str]
     role: str
     department: str
     created_at: datetime
 
 
+class UpdateUserRequest(BaseModel):
+    """Whitelist of updatable user fields."""
+    email: Optional[str] = None
+    username: Optional[str] = None
+    role: Optional[str] = None
+    department: Optional[str] = None
+    clearance_level: Optional[int] = Field(default=None, ge=0, le=3)
+    is_active: Optional[bool] = None
+
+
 class LoginRequest(BaseModel):
```

```diff
--- a/backend/app/api/v1/auth.py
+++ b/backend/app/api/v1/auth.py
@@ -150,8 +150,8 @@
 
-@router.put("/users/{user_id}")
-async def update_user(user_id: int, updates: dict, user=Depends(get_current_user)):
+@router.put("/users/{user_id}")
+async def update_user(user_id: int, updates: UpdateUserRequest, user=Depends(get_current_user)):
     if user.get("role") != "admin": raise HTTPException(403, "Только администратор")
     old = database_service.get_user_by_id(user_id)
     if not old: raise HTTPException(404, "Пользователь не найден")
-    u = database_service.update_user(user_id, updates)
+    u = database_service.update_user(user_id, updates.model_dump(exclude_none=True))
     if not u: raise HTTPException(404, "Пользователь не найден")
     if "is_active" in updates:
```

**Риски:**
- Импорт `UpdateUserRequest` нужно добавить в `auth.py`.
- `model_dump(exclude_none=True)` автоматически исключает не переданные поля.

#### 3b. PUT /document/{doc_id}

**Файл:** [`backend/app/api/v1/graph.py:221-222`](../backend/app/api/v1/graph.py:221)

**Проблема:** `updates: dict` без схемы.

**Решение:** Создать Pydantic-схему и использовать:

```diff
--- a/backend/app/models/schemas.py
+++ b/backend/app/models/schemas.py
@@ -314,3 +314,8 @@
 class DepartmentResponse(BaseResponse):
     id: int
     name: str
     code: str
     description: Optional[str] = None
+
+
+class UpdateDocumentRequest(BaseModel):
+    """Whitelist of updatable document fields."""
+    clearance_level: int = Field(default=0, ge=0, le=3)
+    department: str = Field(default="all", max_length=100)
```

```diff
--- a/backend/app/api/v1/graph.py
+++ b/backend/app/api/v1/graph.py
@@ -219,10 +219,10 @@
 
-@router.put("/document/{doc_id}")
-async def update_document(doc_id: str, updates: dict, current_user=Depends(get_current_user)):
+@router.put("/document/{doc_id}")
+async def update_document(doc_id: str, updates: UpdateDocumentRequest, current_user=Depends(get_current_user)):
     """Обновление clearance_level и department документа в Neo4j + Qdrant."""
     try:
-        clearance_level = updates.get("clearance_level", 0)
-        department = updates.get("department", "all")
+        clearance_level = updates.clearance_level
+        department = updates.department
 
         # Update Neo4j Document node
```

**Риски:** Минимальные — поведение полностью сохраняется.

---

### 4. JWT_SECRET_KEY default "change-me"

**Файл:** [`backend/app/core/config.py:46`](../backend/app/core/config.py:46)

**Проблема:** Если переменная окружения `JWT_SECRET_KEY` не задана, используется `"change-me"`, что делает все JWT токены подписанными известным ключом.

**Решение:** Убрать default, добавить валидацию:

```diff
--- a/backend/app/core/config.py
+++ b/backend/app/core/config.py
@@ -43,8 +43,15 @@
         self.PROJECT_NAME = os.getenv("PROJECT_NAME", "GraphRAG Platform"); self.VERSION = os.getenv("VERSION", "1.0.0")
         self.DESCRIPTION = os.getenv("DESCRIPTION", "Защищённая платформа GraphRAG для корпоративных знаний")
         self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1"); self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true","1","yes")
         self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])
-        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me"); self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
+        jwt_key = os.getenv("JWT_SECRET_KEY")
+        if not jwt_key:
+            if self.ENVIRONMENT == Environment.PRODUCTION:
+                raise RuntimeError(
+                    "JWT_SECRET_KEY must be set in production environment. "
+                    "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
+                )
+            jwt_key = "change-me"
+            logger.warning("jwt_secret_key_default", message="JWT_SECRET_KEY not set, using insecure default for development")
+        self.JWT_SECRET_KEY = jwt_key
+        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
         self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))
```

**Риски:**
- В dev-среде всё将继续 работать с warn-level логом.
- В production приложение не запустится без явного JWT_SECRET_KEY — это intentional.
- Нужен импорт `logger` в `config.py` (если его нет).

---

### 5. Логический баг — мёртвый вызов `get_user_by_id` для setting

**Файл:** [`backend/app/api/v1/admin.py:237`](../backend/app/api/v1/admin.py:237)

**Проблема:** Строка 237 вызывает `database_service.get_user_by_id(audit.setting_id)`, но `audit.setting_id` — это FK на `admin_settings.id`, а не на `user.id`. Этот вызов всегда возвращает None. Правильный код уже есть на строках 241-242.

**Решение:** Удалить строку 237 (мёртвый код).

```diff
--- a/backend/app/api/v1/admin.py
+++ b/backend/app/api/v1/admin.py
@@ -233,8 +233,6 @@
     result: list[dict] = []
     for audit in audit_records:
         # Resolve the setting key and category
-        setting = database_service.get_user_by_id(audit.setting_id)
-        # Actually we need AdminSetting, not User; use a direct query
         from sqlmodel import Session, select
 
         with Session(database_service.engine) as s:
```

**Риски:** 
- Удаление мёртвого кода безопасно. Комментарий на строке 238 уже объясняет, что правильное решение ниже.

---

### 6. Глухие `except: pass` — логирование ошибок

#### 6a. chat.py:78

**Файл:** [`backend/app/api/v1/chat.py:77-78`](../backend/app/api/v1/chat.py:77)

```diff
--- a/backend/app/api/v1/chat.py
+++ b/backend/app/api/v1/chat.py
@@ -75,7 +75,8 @@
     try: database_service.save_message(user_id=current_user["user_id"], role="user", content=last_msg.content)
-    except Exception: pass
+    except Exception as e:
+        logger.warning("save_user_message_stream_failed", error=str(e))
 
     messages = [{"role": m.role, "content": m.content} for m in chat_request.messages]
```

#### 6b. graph.py:93-94, 98-99

**Файл:** [`backend/app/api/v1/graph.py:93-99`](../backend/app/api/v1/graph.py:93)

```diff
--- a/backend/app/api/v1/graph.py
+++ b/backend/app/api/v1/graph.py
@@ -90,14 +90,17 @@
         doc_ids = []
         try:
             async with neo4j_service.session() as s:
                 records = await (await s.run("MATCH (d:Document) RETURN d.id AS doc_id")).data()
                 doc_ids = [r["doc_id"] for r in records]
-        except Exception: pass
+        except Exception as e:
+            logger.warning("clear_get_doc_ids_failed", error=str(e))
         async with neo4j_service.session() as s: await s.run("MATCH (n) DETACH DELETE n")
         from app.services.qdrant_service import qdrant_service as qs
         from app.core.config import settings
         try: await qs._client.delete_collection(settings.QDRANT_COLLECTION)
-        except Exception: pass
+        except Exception as e:
+            logger.warning("clear_qdrant_failed", error=str(e))
         await qs.initialize()
         for doc_id in doc_ids:
             try: s3_service.delete_document(doc_id)
-            except Exception: pass
+            except Exception as e:
+                logger.warning("clear_s3_delete_failed", doc_id=doc_id, error=str(e))
```

#### 6c. s3_service.py:33 — широкий except

**Файл:** [`backend/app/services/s3_service.py:30-34`](../backend/app/services/s3_service.py:30)

```diff
--- a/backend/app/services/s3_service.py
+++ b/backend/app/services/s3_service.py
@@ -5,6 +5,7 @@
 import boto3
 from botocore.config import Config
+from botocore.exceptions import ClientError
 from fastapi import HTTPException
 
 from app.core.config import settings
@@ -27,10 +28,11 @@
 
     def _ensure_bucket(self):
         try:
             self._client.head_bucket(Bucket=settings.S3_BUCKET)
-        except Exception:
-            self._client.create_bucket(Bucket=settings.S3_BUCKET)
-            logger.info("s3_bucket_created", bucket=settings.S3_BUCKET)
+        except ClientError as e:
+            if e.response["Error"]["Code"] == "404":
+                self._client.create_bucket(Bucket=settings.S3_BUCKET)
+                logger.info("s3_bucket_created", bucket=settings.S3_BUCKET)
+            else:
+                logger.warning("s3_bucket_check_failed", error=str(e))
+        except Exception as e:
+            logger.error("s3_bucket_unexpected_error", error=str(e))
+            raise
```

**Риски:** 
- В graph.py:98-99 Qdrant может не быть инициализирован. Сейчас pass скрывает ошибку — после патча будет warning.
- В s3_service.py:33 bucket может не существовать — head_bucket возвращает 404, что попадает под ClientError.
- В graph.py:93 может не быть сессии Neo4j. Warning логируется, выполнение продолжается.

---

### 7. Race Condition TOCTOU — уникальный constraint + try/except

**Файл:** [`backend/app/services/database.py:71-78`](../backend/app/services/database.py:71)

**Проблема:** Проверка `if s.exec(select(User).where(User.email == email)).first()` и затем вставка — между ними может быть конкуренция.

**Решение:** Использовать уникальный constraint на `User.email` + `IntegrityError`:

```diff
--- a/backend/app/services/database.py
+++ b/backend/app/services/database.py
@@ -69,10 +69,13 @@
 
     def create_user(self, email: str, password: str, username: Optional[str] = None) -> User:
         with Session(self.engine) as s:
-            if s.exec(select(User).where(User.email == email)).first():
-                raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
             u = User(email=email, hashed_password=User.hash_password(password), username=username)
-            s.add(u); s.commit(); s.refresh(u)
-            logger.info("user_created", user_id=u.id, email=email)
-            return u
+            try:
+                s.add(u); s.commit(); s.refresh(u)
+                logger.info("user_created", user_id=u.id, email=email)
+                return u
+            except IntegrityError:
+                s.rollback()
+                raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
```

**Нужно также убедиться, что в модели User есть уникальный constraint на email:**

```diff
--- a/backend/app/models/user.py
+++ b/backend/app/models/user.py
@@ -1,4 +1,4 @@
-from sqlmodel import Field
+from sqlmodel import Field, UniqueConstraint
 from app.models.base import BaseModel
 from typing import Optional
 from datetime import datetime, timezone
@@ -9,6 +9,10 @@
 class User(BaseModel, table=True):
     __tablename__ = "user"
+    __table_args__ = (
+        UniqueConstraint("email", name="uq_user_email"),
+    )
```

Аналогично для Department.code:

```diff
--- a/backend/app/services/database.py
+++ b/backend/app/services/database.py
@@ -128,11 +131,14 @@
 
     def create_department(self, name: str, code: str, description: Optional[str] = None) -> Department:
         with Session(self.engine) as s:
-            if s.exec(select(Department).where(Department.code == code)).first():
-                raise HTTPException(409, f"Отдел с кодом '{code}' уже существует")
             d = Department(name=name, code=code, description=description)
-            s.add(d); s.commit(); s.refresh(d)
-            logger.info("department_created", id=d.id, name=name, code=code)
-            return d
+            try:
+                s.add(d); s.commit(); s.refresh(d)
+                logger.info("department_created", id=d.id, name=name, code=code)
+                return d
+            except IntegrityError:
+                s.rollback()
+                raise HTTPException(409, f"Отдел с кодом '{code}' уже существует")
```

**Риски:**
- Для применения уникального constraint нужна новая Alembic миграция (003).
- `IntegrityError` может срабатывать и на другие constraint violations. Для production-grade решения лучше проверять текст ошибки.

---

### 8. XSS в toast()

**Файл:** [`frontend/js/app.js:133-137`](../frontend/js/app.js:133)

**Проблема:** `innerHTML` используется для вставки пользовательского сообщения `m`. Злоумышленник может передать `<img onerror="alert(1)" src=x>`.

**Решение:** Использовать `textContent`:

```diff
--- a/frontend/js/app.js
+++ b/frontend/js/app.js
@@ -128,11 +128,14 @@
 
         const isSticky = opts.sticky === true;
 
-        el.innerHTML =
-            `<span class="toast-msg">${m}</span>` +
-            `<button class="toast-close" style="background:none;border:none;` +
-            `color:var(--text-muted);cursor:pointer;font-size:1.1rem;` +
-            `line-height:1;padding:0;flex-shrink:0;">×</button>`;
+        el.innerHTML = ''; // Clear existing content
+        const msgSpan = document.createElement('span');
+        msgSpan.className = 'toast-msg';
+        msgSpan.textContent = m;
+        el.appendChild(msgSpan);
+        const closeBtn = document.createElement('button');
+        closeBtn.className = 'toast-close';
+        closeBtn.textContent = '×';
+        Object.assign(closeBtn.style, { background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1.1rem', lineHeight: '1', padding: '0', flexShrink: '0' });
+        el.appendChild(closeBtn);
 
         const closeBtn = el.querySelector('.toast-close');
```

> **Примечание:** После изменения `closeBtn` создаётся через `createElement()`, строка `const closeBtn = el.querySelector('.toast-close')` ниже будет находить его. Переименовать переменную для ясности.

**Риски:** 
- Меняется DOM-структура тоста. Убедиться, что CSS-селекторы по классам не сломаны.
- При большом количестве сообщений createElement может быть медленнее innerHTML.

---

### 9. XSS в таблице отделов

**Файл:** [`frontend/js/app.js:527-548`](../frontend/js/app.js:527)

**Проблема:** `d.name`, `d.code`, `d.description` вставляются через `innerHTML` в шаблонной строке.

**Решение:** Добавить функцию экранирования и использовать её:

Добавить в начало файла [`app.js`](../frontend/js/app.js):

```javascript
// Escape HTML to prevent XSS
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}
```

Затем на строках 527-548:

```diff
--- a/frontend/js/app.js
+++ b/frontend/js/app.js
@@ -525,11 +525,11 @@
             tbody.innerHTML = deptList
                 .map((d) => {
                     return `<tr>
-                        <td style="padding:0.5rem;">${d.id}</td>
-                        <td style="padding:0.5rem;"><code>${d.code}</code></td>
+                        <td style="padding:0.5rem;">${escapeHtml(d.id)}</td>
+                        <td style="padding:0.5rem;"><code>${escapeHtml(d.code)}</code></td>
                         <td style="padding:0.5rem;">
-                            <input type="text" value="${d.name}" data-dn="${d.id}"
+                            <input type="text" value="${escapeHtml(d.name)}" data-dn="${escapeHtml(d.id)}"
                                 style="background-color:var(--bg-input);border:1px solid var(--border);
                                 color:var(--text);padding:0.3rem 0.5rem;border-radius:var(--radius);
                                 font-size:0.85rem;width:140px;">
                         </td>
                         <td style="padding:0.5rem;">
-                            <input type="text" value="${d.description || ''}" data-dd="${d.id}"
+                            <input type="text" value="${escapeHtml(d.description)}" data-dd="${escapeHtml(d.id)}"
                                 style="background-color:var(--bg-input);border:1px solid var(--border);
                                 color:var(--text);padding:0.3rem 0.5rem;border-radius:var(--radius);
                                 font-size:0.85rem;width:200px;">
```

**Риски:** Минимальные. `escapeHtml()` — стандартный подход, безопасный для значений в атрибутах.

---

### 10. XSS в таблице документов

**Файл:** [`frontend/js/app.js:1291-1334`](../frontend/js/app.js:1291)

**Проблема:** `doc.title`, `doc.id` вставляются через `${}` в template literal → innerHTML.

**Решение:** Использовать `escapeHtml()`:

```diff
--- a/frontend/js/app.js
+++ b/frontend/js/app.js
@@ -1291,11 +1291,11 @@
                         return `<tr>
                             <td style="padding:0.5rem;">
-                                <span data-dl="${doc.id}"
+                                <span data-dl="${escapeHtml(doc.id)}"
                                     style="color:var(--primary);text-decoration:underline;
                                     cursor:pointer;" title="Скачать документ">
-                                    ${doc.title || doc.id}
+                                    ${escapeHtml(doc.title || doc.id)}
                                 </span>
                             </td>
                             <td style="padding:0.5rem;text-align:center;">
-                                <select data-ddept="${doc.id}" class="form-select"
+                                <select data-ddept="${escapeHtml(doc.id)}" class="form-select"
                                     style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                     ${deptOpts}
```

**Риски:** Минимальные, аналогично п.9.

---

### 11. XSS через marked.parse()

**Файл:** [`frontend/js/app.js:623-634`](../frontend/js/app.js:623)

**Проблема:** `marked.parse(text)` возвращает HTML без санитизации. Если ответ ассистента содержит `<script>` — он выполнится.

**Решение:** Использовать DOMPurify на выходе marked.parse():

```diff
--- a/frontend/js/app.js
+++ b/frontend/js/app.js
@@ -623,8 +623,10 @@
     function renderMd(text) {
         if (typeof marked !== 'undefined') {
             marked.setOptions({ breaks: true });
-            return marked.parse(text);
+            let html = marked.parse(text);
+            return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(html) : html;
         }
```

И добавить DOMPurify в index.html (после marked.js):

```diff
--- a/frontend/index.html
+++ b/frontend/index.html
@@ -556,6 +556,7 @@
     <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
+    <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
```

**Риски:**
- DOMPurify может вырезать легитимный HTML. Проверить, какие теги использует `marked.parse()`.
- CDN-зависимость. Если DOMPurify не загрузится, `typeof DOMPurify` вернёт `undefined` и HTML не будет санитизирован (graceful degradation).

---

## 🟡 HIGH — Критические улучшения

### 1. Синхронный SQLAlchemy в async FastAPI

**Файлы:** [`backend/app/services/database.py`](../backend/app/services/database.py) (весь файл)

**Проблема:** `Session(self.engine)` блокирует event loop при каждом вызове БД. Все ~20 методов DatabaseService синхронные.

**Подход к исправлению:**
1. Заменить `create_engine` на `create_async_engine` с `AsyncSession`.
2. Создать `AsyncDatabaseService` с асинхронными методами.
3. Все вызовы из API-роутеров перевести на `await`.
4. Учесть, что Alembic требует синхронный engine — оставить отдельный `sync_engine`.

### 2. DatabaseService — God Object

**Файл:** [`backend/app/services/database.py`](../backend/app/services/database.py)

**Проблема:** Один класс отвечает за users, departments, sessions, messages, admin_settings, file_metadata — 20+ методов.

**Подход к исправлению:**
- Разделить на: `UserService`, `DepartmentService`, `SessionService`, `MessageService`, `AdminSettingService`, `FileMetadataService`.
- Каждый сервис получает свой engine/session factory.
- Сохранить единый `DatabaseService.__init__` для инициализации engine/миграций.

### 3. Rate Limiting — конфиг есть, middleware нет

**Файлы:** [`backend/app/core/config.py:63-65`](../backend/app/core/config.py:63) (конфиг), **нет middleware**

**Проблема:** Настройки `RATE_LIMIT_DEFAULT` и `RATE_LIMIT_ENDPOINTS` определены, но не используются.

**Подход к исправлению:**
1. Добавить `slowapi` или `aiolimiter` в зависимости.
2. Создать middleware в [`backend/app/core/middleware.py`](../backend/app/core/middleware.py).
3. Интегрировать в [`main.py`](../backend/app/main.py) через `app.add_middleware()` или `@app.middleware()`.

### 4. HS256 вместо RS256 для JWT

**Файл:** [`backend/app/core/config.py:46`](../backend/app/core/config.py:46)

**Проблема:** Симметричный ключ HS256 — если секрет скомпрометирован, можно подделывать токены.

**Подход к исправлению:**
1. Генерировать пару RSA-ключей при развёртывании.
2. Хранить приватный ключ в файле (с ограничением прав) или Vault.
3. Публичный ключ распространять через config/services или встроить в код.
4. Для разработки оставить HS256 как fallback.

### 5. Отсутствие глобального обработчика 401 на фронте

**Файл:** [`frontend/js/api.js`](../frontend/js/api.js)

**Проблема:** При истечении токена во время сессии 401 обрабатывается как обычная ошибка — пользователь не перенаправляется на логин.

**Подход к исправлению:**
1. В `api.js` в базовых HTTP-методах (`get`, `post`, `put`, `del`) добавить проверку статуса 401.
2. При 401: `this.clearToken()` + `window.location.hash = '#login'`.
3. Добавить событие или callback для уведомления UI.

### 6. N+1 запрос в истории настроек

**Файл:** [`backend/app/api/v1/admin.py:237-243`](../backend/app/api/v1/admin.py:237)

**Проблема:** Для каждого audit-записи выполняется отдельный SELECT AdminSetting (строка 242) и SELECT User (строка 247).

**Подход к исправлению:**
1. В `get_admin_settings_history()` добавить `joinedload` или `selectinload` для `AdminSettingsAudit` → `AdminSetting`.
2. Использовать один JOIN-запрос вместо N+1 отдельных.

### 7. 17 S3 запросов вместо batch delete

**Файл:** [`backend/app/services/s3_service.py:99-108`](../backend/app/services/s3_service.py:99)

**Проблема:** `delete_document()` делает 17 отдельных DELETE-запросов (1 для original.txt + 13 для расширений + запас).

**Подход к исправлению:**
```python
def delete_document(self, doc_id: str):
    """Delete all document objects from S3 using batch delete."""
    client = self._get_client()
    # List all objects with prefix
    resp = client.list_objects_v2(
        Bucket=settings.S3_BUCKET,
        Prefix=f"documents/{doc_id}/"
    )
    if "Contents" not in resp:
        return
    keys = [{"Key": obj["Key"]} for obj in resp["Contents"]]
    client.delete_objects(
        Bucket=settings.S3_BUCKET,
        Delete={"Objects": keys, "Quiet": True}
    )
    logger.info("s3_batch_deleted", document_id=doc_id, count=len(keys))
```

### 8. `datetime.utcnow()` deprecated

**Файл:** [`backend/app/models/message.py:19`](../backend/app/models/message.py:19)

**Подход к исправлению:** Заменить `datetime.utcnow()` на `datetime.now(timezone.utc)` как уже сделано в [`models/admin.py:9`](../backend/app/models/admin.py:9).

---

## 🟠 MEDIUM — Долгосрочные улучшения

| # | Файл | Проблема | Подход |
|---|------|----------|--------|
| 1 | [`database.py`](../backend/app/services/database.py) | God Object | Разделить на UserService, DepartmentService, SessionService, MessageService, AdminSettingService, FileMetadataService |
| 2 | [`database.py`](../backend/app/services/database.py) | Синхронный SQLAlchemy | Перейти на async SQLAlchemy 2.0 + asyncpg |
| 3 | [`schemas.py:179-182`](../backend/app/models/schemas.py) | `success` не аннотирован | Добавить `success: bool = False` с аннотацией |
| 4 | [`ingest.py:31`](../backend/app/api/v1/ingest.py) | In-memory статусы | Использовать PostgreSQL/Redis для хранения статусов ингестии |
| 5 | [`document_ingestion.py:269-286`](../backend/app/core/graphrag/document_ingestion.py) | O(n²) overlap | Использовать character-based sliding window |
| 6 | [`admin.py:237-243`](../backend/app/api/v1/admin.py) | N+1 запрос | Eager load через JOIN |
| 7 | [`entity_extraction.py:73-106`](../backend/app/core/graphrag/entity_extraction.py) | Дублирование regex | Единый источник истины в constants.py |
| 8 | [`agent.py:400-409,556-573`](../backend/app/core/langgraph/agent.py) | Дублирование промптов | Вынести в `_build_chat_messages()` |
| 9 | [`schemas.py`](../backend/app/models/schemas.py) | DTO расхождение | Добавить `clearance_level` и `is_active` в `UserResponse` |
| 10 | [`auth.py:26-31`](../backend/app/api/v1/auth.py) | Дублирование SMTP config | Использовать `settings.SMTP_HOST` напрямую |
| 11 | [`vector_indexer.py:42-48`](../backend/app/core/graphrag/vector_indexer.py) | Дублирование BATCH_SIZE | Единый `BATCH_SIZE` из constants |
| 12 | [`neo4j_service.py:36-40`](../backend/app/services/neo4j_service.py) | session() не потокобезопасен | Добавить семафор |
| 13 | [`app.js:209`](../frontend/js/app.js) | Мёртвый код `pollPhase()` | Удалить функцию |
| 14 | [`api.js:100`](../frontend/js/api.js) | Мёртвый код `api.runTests()` | Удалить метод или использовать |

---

## 🔵 LOW — Стилистические замечания

| # | Файл | Проблема | Исправление |
|---|------|----------|-------------|
| 1 | [`database.py:274,288`](../backend/app/services/database.py) | `== True` | Заменить на `.is_(True)` |
| 2 | [`metrics.py:3`](../backend/app/core/metrics.py) | Нет type hints | Добавить аннотации |
| 3 | [`session.py:26`](../backend/app/models/session.py) | UUID как str | Использовать UUID тип PostgreSQL |
| 4 | [`database.py:22`](../backend/app/services/database.py) | Нет `__all__` | Добавить `__all__` для экспорта |
| 5 | [`agent.py:12`](../backend/app/core/langgraph/agent.py) | `quote_plus` не используется | Удалить импорт |
| 6 | [`ingest.py:8,10`](../backend/app/api/v1/ingest.py) | `os`, `Path` не используются | Удалить импорты |
| 7 | [`metrics.py:101`](../backend/app/core/metrics.py) | `import time as _time` | Использовать `import time` |
| 8 | [`neo4j_service.py:178-179`](../backend/app/services/neo4j_service.py) | Нет пустой строки | Добавить отступ |
| 9 | [`app.js:15-17`](../frontend/js/app.js) | Magic string API_BASE | Вынести в единый конфиг |

---

## Архитектурные миграции

### 1. DatabaseService → предметные сервисы

**Текущее состояние:** `DatabaseService` (database.py) — God Object с 20+ синхронными методами.

**План миграции:**

```
Фаза 1 — Выделение сервисов (без изменения API-роутеров):
  1. Создать `services/user_service.py` — UserService
  2. Создать `services/department_service.py` — DepartmentService  
  3. Создать `services/session_service.py` — SessionService
  4. Создать `services/message_service.py` — MessageService
  5. Создать `services/admin_setting_service.py` — AdminSettingService
  6. Создать `services/file_metadata_service.py` — FileMetadataService
  7. Каждый сервис импортирует `settings.postgres_dsn` и создаёт свой engine

Фаза 2 — Переключение импортов:
  8. Заменить `from app.services.database import database_service` на конкретные сервисы
  9. Обновить `__init__.py` для удобного импорта

Фаза 3 — Удаление старого класса:
  10. Удалить `DatabaseService` class
  11. Оставить engine creation для Alembic миграций
```

### 2. Синхронный SQLAlchemy → async

**Текущее состояние:** Все методы DatabaseService используют `with Session(self.engine)` — синхронно.

**План миграции:**

```
Фаза 1 — Подготовка:
  1. Добавить `asyncpg` в зависимости (если нет)
  2. Создать `_create_async_engine()` в config или database.py
  3. Создать `AsyncSession` фабрику

Фаза 2 — Поэтапный перевод:
  4. Перевести UserService на async (первым, т.к. наибольшая нагрузка)
  5. Перевести AdminSettingService (средняя нагрузка)
  6. Перевести остальные сервисы

Фаза 3 — Рефакторинг API-роутеров:
  7. Заменить `database_service.create_user(...)` на `await user_service.create_user(...)`
  8. Учесть, что некоторые вызовы могут быть в синхронном контексте (например, `get_current_user`)
```

### 3. HS256 → RS256 для JWT

**Текущее состояние:** Симметричный ключ HS256.

**План миграции:**

```
Фаза 1 — Генерация ключей:
  1. Добавить скрипт `scripts/generate_jwt_keys.py`:
     openssl genrsa -out jwt-private.pem 2048
     openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
  2. Ключи хранить вне репозитория (в .gitignore)

Фаза 2 — Обновление кода:
  3. В config.py: добавить JWT_PRIVATE_KEY_PATH, JWT_PUBLIC_KEY_PATH
  4. В utils/auth.py: переписать create_access_token и verify_token на RS256
  5. Загружать ключи из файлов при старте

Фаза 3 — Graceful migration:
  6. На первый переходный период принимать и HS256, и RS256 токены
  7. После подтверждения — удалить HS256 поддержку
```

### 4. Реализация недостающих таблиц

**Текущее состояние:** Отсутствуют таблицы `audit_logs` (общий аудит) и `rbac_policies` (политики RBAC).

**План миграции:**

```sql
-- Таблица audit_logs (общий аудит действий пользователей)
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user(id),
    action VARCHAR(64) NOT NULL,        -- created, updated, deleted, login, logout
    entity_type VARCHAR(64) NOT NULL,   -- user, document, department, setting
    entity_id VARCHAR(128),
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица rbac_policies (явные политики доступа)
CREATE TABLE rbac_policies (
    id SERIAL PRIMARY KEY,
    role VARCHAR(32) NOT NULL,
    resource VARCHAR(128) NOT NULL,     -- document, graph, chat, admin
    action VARCHAR(32) NOT NULL,        -- read, write, delete, admin
    conditions JSONB,                   -- дополнительные условия
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 5. Добавление Rate Limiting middleware

**Текущее состояние:** Настройки в config.py есть, код отсутствует.

**План:**

```
1. Добавить aiolimiter в зависимости pyproject.toml
2. Создать `core/ratelimit.py` с middleware:
   - Читать конфиг RATE_LIMIT_ENDPOINTS из settings
   - Использовать in-memory лимитер (с возможностью Redis)
   - Возвращать 429 Too Many Requests с Retry-After
3. В main.py: app.add_middleware(RateLimitMiddleware)
4. Для production: опциональная замена на Redis-based лимитер
```

### 6. Увеличение injection patterns с 13 до 16

**Текущее состояние:** 13 паттернов в [`guardrails.py:81-104`](../backend/app/core/security/guardrails.py:81).

**Недостающие 3 паттерна (из DEFENSE_PLAN.md):**

```python
# Extra injection patterns (3 missing)
r"(?i)you\s+don'?t\s+need\s+to\s+(?:follow|obey)\s+",
r"(?i)new\s+instructions?\s*:",
r"(?i)forget\s+(?:everything|all)\s+(?:you\s+)?(?:know|learned)",
```

**Риски:** Возможны ложные срабатывания — требуется тестирование на корпусе реальных запросов.

---

## Сводная статистика

| Категория | Всего | С патчем | С подходом |
|-----------|-------|----------|------------|
| 🔴 CRITICAL | 11 | 11 | 0 |
| 🟡 HIGH | 8 | 0 | 8 |
| 🟠 MEDIUM | 14 | 0 | 14 |
| 🔵 LOW | 9 | 0 | 9 |
| Архитектурные | 6 | 0 | 6 |
| **ИТОГО** | **48** | **11** | **37** |

---

*План составлен 2026-07-08 на основе трёх аудитов.*
