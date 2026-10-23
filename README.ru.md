<div align="center">

<img src="docs/assets/mark.svg" width="96" height="96" alt="Логотип RLS Doctor">

# RLS Doctor

**Разберитесь в неожиданном поведении авторизации Supabase.**

Соберите метаданные запроса. Проверьте доступ в PostgreSQL. Воспроизведите локальный тест.<br>
Получите факты, ограничения диагностики и следующие шаги.

[**Быстрый старт**](#быстрый-старт) · [Локальная проверка](#локальная-проверка) · [Что проверено](#что-проверено) · [Документация](#документация) · [Релизы](docs/releases.ru.md)

<img src="docs/assets/badges.ru.svg" width="556" height="32" alt="В разработке · Node.js 22.12+ · Python 3.12+ · MIT">

<br><br>

<img src=".github/preview.ru.png" width="880" alt="SDK создаёт обезличенное событие, Python CLI проверяет его формат. Пример проверки контракта без базы данных.">

<sub>Предварительная версия в разработке. Публичных релизов пока нет. <a href="docs/verification.md">Подробности проверок</a>.</sub>

[English](README.md) · **Русский**

</div>

## Возможности

- **Начните с запроса.** Fetch-обёртка для `supabase-js` собирает метаданные REST GET. Запись включается явно.
- **Секреты не попадают в события.** JWT, cookies, пароли, значения фильтров и тела запросов/ответов не сохраняются. Время и объём записи ограничены.
- **Проверьте настройки PostgreSQL.** RLS, FORCE RLS, роли и типы политик, доступ к схеме, таблице и столбцам. Инспектор читает системные каталоги.
- **Воспроизведите локальный тест.** YAML-сценарий задаёт тестовую личность, синтетические значения и ожидаемый результат GET.
- **Отделите факты от гипотез.** Выводы: `OBSERVED`, `INFERRED`, `UNVERIFIED`. Результаты ожиданий: `PASS`, `FAIL`, `UNKNOWN`, `ERROR`.
- **Используйте отчёт в работе.** Консоль, JSON и коды завершения. Без платных API, собственного облака и автоматической телеметрии.

**Ответ `200` с пустым массивом ещё не доказывает блокировку RLS.** Причиной могут быть фильтры, отсутствие данных или контекст авторизации. Если доказательств недостаточно, инструмент показывает неопределённость.

## Быстрый старт

Цепочку SDK → JSON → Python можно проверить без базы данных.

**Требования:** Node.js 22.12+/24, pnpm 11.25.0, Python 3.12+, uv 0.13.5.

```sh
git clone https://github.com/Timon360SB/RLS-Doctor.git
cd RLS-Doctor
pnpm install --frozen-lockfile
uv sync --project python --frozen --group dev
pnpm build

node examples/node-basic/capture-event.mjs > event.json
uv run --project python rls-doctor validate event.json --format json
```

Пример использует настоящую Fetch-обёртку с ответом в памяти и проверяет событие в Python. Это проверка контракта; поведение Supabase и базы данных проверяется отдельно. Пакеты устанавливаются из репозитория — публикаций в npm и PyPI пока нет.

## Локальная проверка

Подготовьте [одноразовое окружение Supabase](fixtures/README.md) с Docker и Supabase CLI 2.121.0, затем создайте и проверьте конфигурацию:

```sh
uv run --project python rls-doctor init
uv run --project python rls-doctor doctor
uv run --project python rls-doctor inspect public.documents
uv run --project python rls-doctor replay documents.yaml --inspect --format json
```

После `init` выполнение выключено. Разрешите конкретный локальный IP-адрес, порты и ресурсы, передайте тестовые учётные данные через переменные окружения. Настройка и полный E2E — в [инструкции запуска](docs/getting-started.md).

Примеры: [нет ожидаемой авторизации](examples/missing-auth/scenario.yaml), [default-deny](examples/incorrect-rls/scenario.yaml), [нет GRANT](examples/missing-grant/scenario.yaml), [нарушение изоляции](examples/tenant-isolation/scenario.yaml). Некоторые намеренно завершаются `FAIL`.

## Что проверено

| Часть проекта | Наблюдаемый результат |
| --- | --- |
| TypeScript SDK | 46 локальных тестов прошли |
| Python и общий контракт | 76 локальных тестов прошли |
| Инспектор PostgreSQL | 8 реальных интеграционных тестов прошли на PostgreSQL 17.10 |
| Python-пакет | Wheel собран, установлен и проверен через CLI |
| Полный Supabase Auth + REST E2E | Код и окружение подготовлены; выполнение ещё не проверено |
| GitHub Actions и независимое ревью | Ещё не подтверждены |

<sub>Снимок локальных проверок от 23.10.2026. Это не результат текущего CI. <a href="docs/verification.md">Полный отчёт</a>.</sub>

До стабильного релиза нужны полный Supabase E2E, подтверждённый CI и независимое ревью. Инструмент не доказывает защищённость приложения в целом.

## Документация

- [Запуск](docs/getting-started.md) и [API SDK](packages/capture-sdk/README.md).
- [Архитектура](docs/architecture.md), [разработка](docs/development.md), [исследование аналогов](docs/research.md).
- [Безопасность](docs/security.md), [ограничения](docs/limitations.md), [решение проблем](docs/troubleshooting.md).
- [Релизы](docs/releases.ru.md), [история изменений](CHANGELOG.md), [оформление GitHub](docs/github-appearance.ru.md).

Основная техническая документация ведётся на английском.

## Участие и лицензия

[Создайте issue](https://github.com/Timon360SB/RLS-Doctor/issues) с обезличенным описанием и синтетическим примером. Перед изменениями прочитайте [CONTRIBUTING.md](CONTRIBUTING.md), перед сообщением об уязвимости — [SECURITY.md](SECURITY.md).

Лицензия [MIT](LICENSE). Инструкции для разработки — в [AGENTS.md](AGENTS.md).
