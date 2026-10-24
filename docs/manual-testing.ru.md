# Как самостоятельно проверить RLS Doctor на Windows

Эта инструкция рассчитана на **PowerShell**, команды выполняются из корня
репозитория. Начните с раздела без Docker, затем переходите к настоящему
локальному Supabase. Для тестов используются только синтетические данные
из этого проекта.

Инструкция описывает ожидаемое поведение; она сама по себе не означает, что
полный E2E уже прошёл на вашем компьютере. На начало работы Docker и Supabase CLI
на этой Windows-машине отсутствовали. Предыдущий удалённый E2E завершился ошибкой
проверки локального API-ключа; исправление требует полного повторного прогона.
Проверенные запуски и актуальные ограничения перечислены в
[журнале проверок](verification.md).

## 1. Подготовьте PowerShell и инструменты

Откройте отдельное окно PowerShell и перейдите в папку проекта:

```powershell
Set-Location 'C:\Users\sbtim\Documents\GitHub\RLS-Doctor'
git status --short
node --version
pnpm --version
uv --version
```

Требуются Node.js **22.12+ или 24**, pnpm **11.25.0**, Python **3.12+** и uv
**0.13.5**. Локальная базовая проверка выполнялась на Node 24 и Python 3.12.
Команда `uv sync` ниже может подобрать/скачать подходящий Python.
Если команда не найдена, сначала установите соответствующий инструмент и заново
откройте PowerShell. Докер понадобится только для раздела 7.

Не используйте подключение к рабочему Supabase-проекту и настоящие пользовательские
данные. Не включайте `Start-Transcript`, отладочную печать HTTP или запись
вывода `supabase status`: там могут находиться локальные ключи и строки подключения.
Значения ключей, паролей и токенов не нужно вставлять в чат, Git, issue или отчёт.

Установите зависимости по lock-файлам и соберите SDK. Выполняйте команды по одной;
если установка или сборка завершилась ненулевым кодом, сначала исправьте её ошибку:

```powershell
pnpm install --frozen-lockfile
uv sync --project python --frozen --group dev
pnpm build
uv run --project python rls-doctor --help
```

Ожидается успешная сборка и список команд `init`, `validate`, `analyze`, `doctor`, `inspect`,
`replay`. Для проверки `$LASTEXITCODE` смотрите его **сразу после** соответствующей
команды: следующая внешняя программа перезапишет значение.

## Можно проверить без Docker

## 2. Получите событие SDK и проверьте его в Python

Создайте папку для временных, игнорируемых Git файлов:

```powershell
New-Item -ItemType Directory -Force -Path '.rls-doctor/manual' | Out-Null
$rlsUtf8 = [System.Text.UTF8Encoding]::new($false)
$rlsEventLines = & node examples/node-basic/capture-event.mjs
if ($LASTEXITCODE -ne 0) { throw 'Не удалось получить событие SDK; проверьте pnpm build.' }
$rlsEventPath = Join-Path (Get-Location).Path '.rls-doctor/manual/event.json'
[System.IO.File]::WriteAllText($rlsEventPath, ($rlsEventLines -join "`n"), $rlsUtf8)
uv run --project python rls-doctor validate .rls-doctor/manual/event.json --format json
Write-Host "Код завершения: $LASTEXITCODE"
```

Ожидается `"result": "PASS"`, `"schema_version": "1.0"`, ресурс `documents` и
код **0**. Идентификатор события и время при повторе меняются.

Здесь применяется настоящая Fetch-обёртка SDK, но ответ `[]` создаётся в памяти.
Сеть, Docker, учётные данные и база данных не используются. Этот шаг доказывает
совместимость SDK → JSON → Python, а не правильность RLS.

**Почему запись сделана через `WriteAllText`:** загрузчик CLI читает строго UTF-8.
В Windows PowerShell 5.1 перенаправление `> event.json` обычно создаёт UTF-16, а
`Set-Content -Encoding utf8` добавляет BOM. Оба варианта могут испортить этот тест.
Показанная команда сохраняет UTF-8 без BOM и работает также в PowerShell 7.

Можно открыть `.rls-doctor/manual/event.json` редактором. В нём должны быть только
разрешённые метаданные. У фильтра остаются имя `owner_id` и оператор `eq`, а
значение `synthetic-fixture-value` отсутствует. Сам файл этого примера не содержит
ключей или строк таблицы.

## 2а. Разберите событие без базы данных

```powershell
uv run --project python rls-doctor analyze .rls-doctor/manual/event.json --expected-role authenticated --format json
Write-Host "Код анализа: $LASTEXITCODE"
```

Ожидается `UNKNOWN` и код **2**. Это выполненный офлайн-анализ, а не ошибка
формата. В примере отсутствует Authorization, поэтому среди фактов будет
`MISSING_EXPECTED_AUTH` с `OBSERVED`. Пустой ответ отражается как
`EMPTY_RESULT_AMBIGUOUS` с `UNVERIFIED`: по нему нельзя установить причину RLS.
Поле `confirmed_role` остаётся `null`; наличие заголовка тоже не доказывало бы роль.

Без `--expected-role` инструмент не выдумывает ожидание авторизованного запроса.
Для текстового отчёта уберите `--format json`. Ключи окружения, конфигурация
локального стека и Docker для этой команды не нужны. `validate` проверяет формат
события, а `analyze` объясняет доступные метаданные и их ограничения.

## 3. Убедитесь, что неверное событие отклоняется

Не меняйте исходное событие: сохраните отдельную копию с неподдерживаемой версией.

```powershell
$rlsBadEvent = Get-Content -Raw -LiteralPath $rlsEventPath | ConvertFrom-Json
$rlsBadEvent.schema_version = '99.0'
$rlsBadEventPath = Join-Path (Get-Location).Path '.rls-doctor/manual/invalid-event.json'
$rlsBadEventJson = $rlsBadEvent | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($rlsBadEventPath, $rlsBadEventJson, $rlsUtf8)
uv run --project python rls-doctor validate .rls-doctor/manual/invalid-event.json --format json
Write-Host "Код завершения: $LASTEXITCODE"
```

Ожидается `ERROR`, код ошибки `INVALID_EVENT`, код завершения **3**. Это успешная
проверка отказа от неподдерживаемого формата. Если здесь получился `PASS`, это дефект.

## 4. Проверьте, что replay изначально выключен

```powershell
uv run --project python rls-doctor init --directory .rls-doctor/manual
uv run --project python rls-doctor doctor --config .rls-doctor/manual/rls-doctor.toml --format json
Write-Host "Код завершения: $LASTEXITCODE"
```

`init` создаёт `rls-doctor.toml` и `documents.yaml`. Ожидается
`approved_local = false` в TOML; последующий `doctor` должен вернуть **ERROR / 3**
с `LOCAL_APPROVAL_REQUIRED`, прежде чем начнёт работу с сетью или БД.
Так проверяется обязательное явное включение локального тестирования.

При повторном `init` существующие файлы не перезаписываются: `INIT_EXISTS` означает,
что нужно использовать уже созданную конфигурацию или выбрать новую пустую папку.
Пока не включайте `approved_local`: это делается после проверки назначения среды.

## 5. Запустите автоматические проверки кода

```powershell
pnpm build
pnpm typecheck
pnpm lint
pnpm test
uv run --project python ruff format --check python scripts
uv run --project python ruff check python scripts
uv run --project python pytest python/tests -m 'not integration' -q
Push-Location python
try { uv run mypy } finally { Pop-Location }
```

Каждая команда должна закончиться кодом **0**. В обычном режиме без локальной БД
интеграционные тесты в эту проверку не входят. Число тестов может меняться по мере
разработки; важнее отсутствие `failed` и ненулевых кодов. Перед Python contract
тестами нужен `pnpm build`: Python вызывает реальный собранный SDK.

Если запустить `uv run --project python pytest python/tests -q` без переменных
локальной интеграции, часть тестов БД будет `skipped`. Это не доказательство того,
что база данных проверена. Реальную Auth/REST/БД-цепочку проверяет раздел 8.

## 6. Как читать результаты

| Результат CLI | Код | Что это означает |
| --- | --- | --- |
| `PASS` | `0` | Наблюдение совпало с заданным ожиданием. Ожидаемый отказ HTTP тоже может быть PASS. |
| `FAIL` | `1` | Наблюдение не совпало с ожиданием. В отрицательных демонстрациях это предусмотрено. |
| `UNKNOWN` | `2` | Для вывода недостаточно данных. Это не успешная проверка поведения. |
| `ERROR` | `3` | Проверка не выполнена: конфигурация, формат, соединение, учётные данные или другая операционная ошибка. |

Отдельно `OBSERVED`, `INFERRED`, `UNVERIFIED` описывают уровень доказательств в
выводах, а не коды завершения. `200` с `row_count: 0` не доказывает запрет RLS:
возможны фильтры, отсутствующая строка или другой контекст выполнения.

## Нужен Docker

## 7. Поднимите только одноразовый локальный Supabase

Установите Docker Desktop с Linux-контейнерами и запустите его. Первичная настройка
Windows/WSL может потребовать прав администратора и перезагрузки; после неё заново
откройте PowerShell в корне репозитория. Установите Supabase CLI **2.121.0**.

Проверьте готовность:

```powershell
docker version
docker info --format '{{.OSType}}'
supabase --version
```

У `docker version` должны отвечать клиент и сервер; тип контейнеров — `linux`.
Если сервер недоступен, запустите Docker Desktop и дождитесь готовности движка.

В проекте уже есть конфигурация `fixtures/supabase/config.toml`, миграция и seed.
API использует `127.0.0.1:54321`, PostgreSQL — `127.0.0.1:54322`, выбран PostgreSQL 17.
Порты должны быть свободны. Не меняйте `workdir`, не выполняйте `supabase link`
или `supabase db push` и не подставляйте удалённый проект.

Запустите фикстуры без вывода потенциально секретных startup-данных:

```powershell
& supabase start --workdir fixtures *> $null
$rlsStartExit = $LASTEXITCODE
if ($rlsStartExit -ne 0) { throw 'Локальные фикстуры не запустились. Проверьте Docker и занятость портов.' }
```

Первый запуск скачивает образы и может занять несколько минут. Не запускайте
повторно ту же команду, пока она работает. Миграции создают четыре тестовые таблицы;
в каждой только две заведомо синтетические строки.

## 8. Выполните полный автоматический E2E

Этот этап **создаёт двух временных локальных Auth-пользователей и обновляет
владельцев синтетических строк**. Такие записи нужны для подготовки фикстур;
сама диагностика выполняет GET и читает системные каталоги. Переменная ниже —
ваше явное согласие на подготовку этой одноразовой среды.

```powershell
$env:RLS_DOCTOR_ALLOW_FIXTURE_SETUP = '1'
supabase status --workdir fixtures --output json 2>$null |
    uv run --project python python scripts/e2e.py --status-stdin
$rlsE2eExit = $LASTEXITCODE
Write-Host "Код E2E: $rlsE2eExit"
if ($rlsE2eExit -ne 0) { throw 'Полный E2E не прошёл. Запишите только безопасный код ошибки из вывода.' }
```

Не выполняйте `supabase status` отдельно без перенаправления в проверяющий процесс
и не сохраняйте его JSON на диск. Здесь ключи передаются через stdin и остаются
в памяти процесса. Токены и пароли не возвращаются в родительский PowerShell.
Повторный E2E создаёт новых временных пользователей и снова назначает владельцев
тестовых строк, поэтому не запускайте параллельно другие проверки этой же среды.

Успешный прогон заканчивается кодом **0** и строками `PASS`, включая:

- `actual supabase-js GET -> Capture SDK -> JSON Schema -> Python`;
- `own_row_and_other_user_denial` и `second_test_user`;
- `missing_auth`, `default_deny`, `missing_grant`, `tenant_isolation_leak`;
- `nonexistent_row_ambiguity`;
- `invalid test token rejected before transmission`;
- `real PostgreSQL inspector integration suite`.

Здесь `PASS default_deny` или `PASS tenant_isolation_leak` означает, что тест
правильно обнаружил предусмотренное несовпадение ожиданий: вложенный replay
вернул ожидаемый `FAIL`. Это не утверждение, что неправильная политика допустима.
При ненулевом коде весь E2E считается незавершённым, даже если первая строка о
capture уже была `PASS`.

## 9. Откройте отдельную ручную тестовую сессию

После E2E учётные данные остаются в завершившемся дочернем процессе. Поэтому
простая команда `replay` из родительского PowerShell ещё не заработает.
Для отдельных ручных команд предусмотрена специальная локальная сессия:

```powershell
$env:RLS_DOCTOR_ALLOW_FIXTURE_SETUP = '1'
uv run --project python python scripts/manual_session.py
```

Запускайте эту команду напрямую в обычном интерактивном терминале PowerShell,
без `|`, перенаправления stdin и записи транскрипта. Ошибка
`INTERACTIVE_TERMINAL_REQUIRED` означает, что скрипту нужен такой терминал.

Скрипт сам получает локальное состояние Supabase, готовит новую пару временных
пользователей и назначает им синтетические строки. Затем он открывает дочерний
PowerShell в корне репозитория. Ключи, DSN и токен находятся только в окружении
этого дочернего процесса. Значения не нужно узнавать, копировать или сохранять.
Не запускайте одновременно E2E и ручную сессию: обе подготовки меняют владельцев
одних и тех же тестовых строк.

Только **внутри открывшегося дочернего PowerShell** задайте короткие пути:

```powershell
$rlsSessionPath = $env:RLS_DOCTOR_MANUAL_SESSION
if (-not $rlsSessionPath) { throw 'Это не дочерняя тестовая сессия RLS Doctor.' }
$rlsConfig = Join-Path $rlsSessionPath 'rls-doctor.toml'
```

Сессионная папка находится под `.rls-doctor/`, она игнорируется Git. В ней
конфигурация и YAML-сценарии с синтетическими значениями; секретов в этих файлах
нет. Проверьте `rls-doctor.toml` редактором: `127.0.0.1`, API-порт `54321`,
DB-порт `54322`, четыре fixture-таблицы и `confirm_identity = true`.

В отличие от отключённого шаблона из шага 4, **сессионный** TOML содержит
`approved_local = true`: включение разрешается вашим явным запуском helper с
согласием на одноразовую среду. Исходный `.rls-doctor/manual/rls-doctor.toml`
из `init` остаётся выключенным. Для собственной конфигурации надо сначала
проверить IP, порты и ресурсы и только затем вручную поставить
`approved_local = true`; одних ключей окружения недостаточно.

## 10. Проверьте среду и прочитайте каталоги PostgreSQL

```powershell
uv run --project python rls-doctor doctor --config $rlsConfig --format json
Write-Host "Код doctor: $LASTEXITCODE"
uv run --project python rls-doctor inspect public.documents --role authenticated --config $rlsConfig --format json
Write-Host "Код inspect: $LASTEXITCODE"
uv run --project python rls-doctor inspect public.no_grant_documents --role authenticated --config $rlsConfig --format json
Write-Host "Код inspect: $LASTEXITCODE"
```

Ожидания:

- `doctor`: **PASS / 0**, локальный API и БД доступны, поддерживаемая версия
  и исполняемая роль проверены доверенным fixture-probe.
- `inspect public.documents`: **UNKNOWN / 2** — это предусмотрено. Отчёт
  показывает подтверждённые факты каталога, например RLS и SELECT-политику,
  но не заявляет, что поведение запроса уже доказано.
- `inspect public.no_grant_documents`: также **UNKNOWN / 2**; среди выводов
  `conclusions` должен быть `SELECT_PRIVILEGE_MISSING`. Отсутствующий GRANT
  и RLS-политика — разные механизмы доступа.

Если `doctor` возвращает ERROR или UNKNOWN, сначала разберите эту причину;
не считайте последующие сценарии успешно проверенными.

## 11. Сравните положительный и отрицательные replay-сценарии

Запустите сценарий доступа первого тестового пользователя:

```powershell
$rlsOwnRow = Join-Path $rlsSessionPath 'own-row.yaml'
uv run --project python rls-doctor replay $rlsOwnRow --config $rlsConfig --inspect --format json
Write-Host "Код own-row: $LASTEXITCODE"
```

Ожидается **PASS / 0**, HTTP `200`, `row_count: 1`, `confirmed_role: authenticated`.
В сценарии проверяется не только число строк: собственная строка с синтетическим
ID, заканчивающимся `0001`, должна присутствовать, а чужая с `0002` — отсутствовать.
Фактические строки в отчёт не копируются. Проверка второго авторизованного
пользователя отдельно включена в полный E2E шага 8.

Запустите четыре подготовленных примера по одному:

```powershell
$rlsScenario = Join-Path $rlsSessionPath 'missing-auth.yaml'
uv run --project python rls-doctor replay $rlsScenario --config $rlsConfig --inspect --format json
Write-Host "Код missing-auth: $LASTEXITCODE"
$rlsScenario = Join-Path $rlsSessionPath 'default-deny.yaml'
uv run --project python rls-doctor replay $rlsScenario --config $rlsConfig --inspect --format json
Write-Host "Код default-deny: $LASTEXITCODE"
$rlsScenario = Join-Path $rlsSessionPath 'missing-grant.yaml'
uv run --project python rls-doctor replay $rlsScenario --config $rlsConfig --inspect --format json
Write-Host "Код missing-grant: $LASTEXITCODE"
$rlsScenario = Join-Path $rlsSessionPath 'tenant-isolation.yaml'
uv run --project python rls-doctor replay $rlsScenario --config $rlsConfig --inspect --format json
Write-Host "Код tenant-isolation: $LASTEXITCODE"
```

| Пример | Ожидаемый результат | Что проверяется |
| --- | --- | --- |
| `missing-auth` | **FAIL / 1**; HTTP 200, 0 строк, роль anon | Сценарий ожидает authenticated и одну строку, хотя отправляет анонимный GET. |
| `default-deny` | **FAIL / 1**; HTTP 200, 0 строк | Есть SQL GRANT, но нет разрешающей SELECT-политики; ожидание одной строки не выполнено. |
| `missing-grant` | **PASS / 0**; HTTP 403, `error_class: permission` | Ожидаемый отказ доступа обнаружен: политика не заменяет отсутствующий GRANT. |
| `tenant-isolation` | **FAIL / 1**; HTTP 200, 2 строки | Намеренно неправильная политика раскрыла обе синтетические строки вместо одной. |

**Эти FAIL предусмотрены.** Они демонстрируют обнаружение проблем в фикстурах,
а не поломку CLI. Не меняйте ожидания только ради зелёного отчёта.

Можно открыть YAML редактором, сравнить `expect` с отчётом и сделать собственную
копию сценария внутри сессионной папки. Replay принимает только GET и
разрешённые таблицы. Токен в YAML представлен именем переменной окружения,
а не значением. Разрешённые фильтры: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `is`;
произвольные SQL/RPC и операции записи не поддерживаются.

## 12. Проверьте неоднозначный пустой ответ и неверный токен

```powershell
$rlsScenario = Join-Path $rlsSessionPath 'nonexistent-row.yaml'
uv run --project python rls-doctor replay $rlsScenario --config $rlsConfig --format json
Write-Host "Код nonexistent-row: $LASTEXITCODE"
```

Ожидается **PASS / 0**, HTTP `200` и `row_count: 0`, но также
`EMPTY_RESULT_AMBIGUOUS` с `UNVERIFIED`. PASS подтверждает только ожидание пустого
ответа. Здесь фильтр выбирает отсутствующую синтетическую строку; одного
HTTP-ответа недостаточно, чтобы объявить причиной RLS.

Следующая проверка временно подставляет заведомо неверный локальный токен и затем
восстанавливает правильный. Сам правильный токен не печатается:

```powershell
$rlsSavedToken = $env:RLS_DOCTOR_TEST_TOKEN
try {
    $env:RLS_DOCTOR_TEST_TOKEN = 'invalid-local-token'
    uv run --project python rls-doctor replay $rlsOwnRow --config $rlsConfig --format json
    Write-Host "Код invalid-token: $LASTEXITCODE"
} finally {
    $env:RLS_DOCTOR_TEST_TOKEN = $rlsSavedToken
    Remove-Variable rlsSavedToken -ErrorAction SilentlyContinue
}
```

Ожидается **ERROR / 3**, `INVALID_TEST_TOKEN`. Это предусмотренное защитное
отклонение до отправки пользовательского replay-запроса. Для проверки подписи
асимметричного JWT может использоваться разрешённый локальный JWKS.
Обычные локальные токены истекают: если при долгой работе валидный сценарий
стал возвращать `INVALID_TEST_TOKEN`, закройте сессию и запустите helper заново.

## 13. Завершите работу

Завершите именно дочернюю тестовую сессию:

```powershell
exit
```

Вы вернётесь в исходный PowerShell. Переменные с локальными ключами и токеном
дочернего процесса не переходят в него. Остановите fixture-проект RLS Doctor:

```powershell
& supabase stop --workdir fixtures *> $null
$rlsStopExit = $LASTEXITCODE
Write-Host "Код остановки: $rlsStopExit"
Remove-Item -LiteralPath Env:RLS_DOCTOR_ALLOW_FIXTURE_SETUP -ErrorAction SilentlyContinue
git status --short
```

Обычная остановка сохраняет локальные Docker-данные для следующего запуска.
Для повторного чистого seed существует `supabase db reset --workdir fixtures`,
но эта команда уничтожает изменения данных **этой локальной среды**. Применяйте
её только осознанно к одноразовым фикстурам, затем заново готовьте пользователей
и владельцев строк. Всегда проверяйте папку, workdir и локальную конфигурацию.

В Git не должны появиться файлы с ключами, токенами, DSN или JSON `supabase status`.
`.rls-doctor/` уже игнорируется; временные события и YAML можно удалить позже.
Сам факт игнорирования не делает произвольный файл безопасным для пересылки.

## 14. Что сообщить при проблеме

Достаточно команды, версий инструментов, названия синтетического сценария,
результата/кода завершения и безопасного кода вроде `LOCAL_APPROVAL_REQUIRED`,
`INVALID_EVENT`, `INVALID_TEST_TOKEN` или `POSTGRES_INSPECTION_FAILED`.
Не прикладывайте startup/status-вывод Supabase, сырые HTTP-ошибки, значения
переменных окружения, токены или данные приложения.

Если сбой произошёл на первом запуске Docker, это ещё не результат диагностики
RLS. Если E2E показал несколько PASS, а затем ERROR, полный E2E не прошёл.
Дополнительные пояснения: [решение проблем](troubleshooting.md),
[ограничения](limitations.md), [устройство фикстур](../fixtures/README.md).

