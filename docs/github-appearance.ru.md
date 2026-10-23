# Оформление репозитория GitHub

[English](github-appearance.md) · **Русский**

## Главная страница

README.md — английская главная страница, README.ru.md — русская. Сверху есть переключатель языка. Иконка, бейджи, изображение CLI и Social preview созданы для RLS Doctor. Центрированный первый экран и крупное превью ориентируются на [Free My TV](https://github.com/simbasjungles/free-my-tv); его логотип, скриншот и утверждения о продукте не переносились.

В превью показана часть фактического вывода **локальной проверки контракта без базы данных**. Оно не изображает неподтверждённую live-диагностику. Бейджи показывают этап разработки и требования, а не успешный CI.

Все изображения находятся в репозитории. Исходники SVG доступны в assets/. Крупное превью английской страницы — `.github/preview.png`, русской — `.github/preview.ru.png`. Подписи изображений переведены; команды, имена полей и результаты CLI сохранены в исходном виде.

## Краткое описание About

Нажмите шестерёнку рядом с **About**. Для международного репозитория подойдёт:

> Request capture, local replay and evidence-based authorization diagnostics for Supabase and PostgreSQL RLS.

Русский вариант:

> Захват метаданных запросов, локальное воспроизведение и диагностика авторизации Supabase и PostgreSQL RLS на основе проверяемых фактов.

GitHub хранит одно описание About; выберите язык. Предлагаемые темы:

`supabase`, `postgresql`, `row-level-security`, `rls`, `developer-tools`, `authorization`, `typescript`, `python`, `cli`, `open-source`

Поле Website оставьте пустым, пока у проекта нет настоящего сайта. Удалённые настройки репозитория этим изменением не менялись. [Темы репозитория: инструкция GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics).

## Обложка ссылки

В **Settings → Social preview → Edit → Upload an image** загрузите **docs/assets/social-preview.ru.png**. Размер — 1280 × 640, файл меньше 1 МБ. Редактируемый исходник — social-preview.ru.svg. Для английской обложки используйте social-preview.png. GitHub позволяет выбрать одну обложку репозитория; она не переключается вместе с языком README. Это обложка для ссылок, отдельная от крупного изображения внутри README. [Официальная инструкция](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Как показать оформление на GitHub

Сделайте commit файлов оформления в текущей ветке и Push origin. Затем создайте Pull Request в main, проверьте изменения и дождитесь настроенных проверок. После объединения README появится на основной странице по умолчанию. Релиз создаётся отдельно — см. [инструкцию](releases.ru.md).

Название коммита: `docs: add bilingual project pages and release guides`.

Перевод: «Добавить двуязычные страницы проекта и инструкции по релизам».
