# GitHub repository appearance

**English** · [Русский](github-appearance.ru.md)

## Main page

The root README is the English landing page; README.ru.md is its Russian counterpart. Both link to each other. The icon, badges, CLI preview and social preview are original RLS Doctor assets. The centered hierarchy and product-preview layout were informed by [Free My TV](https://github.com/simbasjungles/free-my-tv); its logo, screenshot and product claims were not reused.

The CLI image shows selected output from a real **offline contract validation**. It does not present a simulated live database diagnosis as a verified result. Badges describe development status and declared runtime requirements; they do not claim green CI.

The assets are local to the repository. Editable vector sources are in assets/. The README hero is `.github/preview.png` (English) and `.github/preview.ru.png` (Russian).

## About

On the repository page, use the gear beside **About** to edit metadata. Suggested description:

> Request capture, local replay and evidence-based authorization diagnostics for Supabase and PostgreSQL RLS.

Suggested topics:

`supabase`, `postgresql`, `row-level-security`, `rls`, `developer-tools`, `authorization`, `typescript`, `python`, `cli`, `open-source`

Leave Website empty until a real project website exists. Do not enter a placeholder domain. This local change has not modified remote repository metadata. [GitHub topics guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics).

## Social preview

Upload **docs/assets/social-preview.png** through **Settings → Social preview → Edit → Upload an image**. It is 1280 × 640 PNG, below 1 MB. Its editable source is social-preview.svg. This is the link-sharing image, separate from the README hero. [GitHub social preview guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Publish the new page

Commit the documentation/assets in the current feature branch and push it. Create a PR into main, review the diff and let the configured checks run. After merge, the default repository page will show this README. A GitHub release is a separate action; see [releases](releases.md).

Suggested commit subject: `docs: add bilingual project pages and release guides`.

Russian image variants use the `.ru` suffix. Commands and JSON fields remain unchanged. GitHub has one social preview image per repository; choose the English or Russian cover when uploading.
