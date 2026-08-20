---
title: Базы данных
parent: Руководство пользователя
nav_order: 7
permalink: user-guide/databases
lang: ru
---

# Базы данных

{: .no_toc}

RimSort использует внешние базы для сортировки и зависимостей. Они не в релизе — есть инструменты установки и обновления. Для базовой работы не обязательны, но улучшают UX.

Настройка: **Settings → Databases**.

## Содержание

{: .no_toc .text-delta }

1. TOC
{:toc}

## Community Rules Database

Правила порядка загрузки от сообщества. Авторам лучше указывать правила в `about.xml`, но не всегда. CR DB — публичный репозиторий дополнительных правил с комментариями, включая RimSort-специфичные (например **Force load at bottom of list**).

## User Rules Database

`userRules.json` — локальные пользовательские правила. Создаётся автоматически в папке databases. Приоритетнее community rules, редактируется в Rule Editor.

## Use This Instead Database

Опциональная БД с заменами устаревших или несовместимых модов. Источник в настройках, часто [Use This Instead Mod](https://steamcommunity.com/sharedfiles/filedetails/?id=3396308787).

## No Version Warning Database

`ModIdsToFix.xml` — packageId без предупреждений о версии. Для модов без версии в `about.xml` или с несколькими версиями игры. Источник: [No Version Warning Mod](https://steamcommunity.com/sharedfiles/filedetails/?id=2599504692).

## Steam Workshop Database

{: .note}
> Сборка и обновление — [Сборщик БД](db-builder)

Steam DB — дополнительные зависимости из Workshop. Статическая БД даёт данные без скачивания каждого мода.

## Git в RimSort

### _**Нужен**_ [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

Для `steamDB.json` и `communityRules.json`.

{: .important}
> GitHub-учётные данные в Advanced нужны только для PR из RimSort. Для клонирования публичных репозиториев — не обязательны.

1. [Создайте репозиторий](https://docs.github.com/en/get-started/quickstart/create-a-repo) или используйте существующий.
2. URL в **Settings → Databases**.
3. **(Опционально)** GitHub в **Advanced** — PAT с правом `Repo`.
4. Делитесь изменениями БД через встроенные функции.

### Клонирование БД

{: .warning}
> Видео может быть устаревшим.

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/2c236e00-d963-4831-93e7-3effb10c6b5e" frameborder="0" allowfullscreen="true" alt="Download Database Demo Video"></iframe>

### Загрузка (нужны права на репозиторий)

{: .warning}
> Видео может быть устаревшим.

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/60ced0ef-adba-436f-8fbc-e593a236e389" frameborder="0" allowfullscreen="true" alt="Upload Database Demo Video"></iframe>
