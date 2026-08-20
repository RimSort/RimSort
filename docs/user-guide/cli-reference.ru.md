---
title: Справочник CLI
nav_order: 8
layout: default
parent: Руководство пользователя
permalink: user-guide/cli-reference
lang: ru
---

# CLI

{: .no_toc}

Командная строка для headless-режима: автоматизация, CI/CD, скрипты без GUI.

## Содержание

{: .no_toc .text-delta }

1. TOC
{:toc}

## Обзор

CLI RimSort для серверов и контейнеров:

- **Без display server** — Docker, CI/CD
- **Коды выхода** — для скриптов
- **Переменные окружения** — ключи без истории shell
- **Без Qt** — минимальные зависимости

Сейчас: `build-db` — сборка метаданных Workshop. Другие команды могут появиться позже.

## Запуск

Релиз:

```bash
./RimSort build-db --help
```

Windows:

```bash
RimSort.exe build-db --help
```

Из исходников:

```bash
python -m app build-db --help
uv run python -m app build-db --help
```

## Команды

### `build-db`

Сборка Steam Workshop DB через WebAPI: имена, URL, зависимости, опционально DLC. JSON совместим с RimSort и RimPy.

#### Требования

**Steam WebAPI Key**
{: .d-inline-block}
Обязательно
{: .label .label-red }

{: .important }
Ключ WebAPI — в [Сборщик БД](db-builder#как-получить-steam-webapi-ключ).

{: .warning}
Нужна RimWorld в Steam. Обычно $5+ на аккаунте для WebAPI и Steamworks (DLC).

Ключ — 32 символа.

#### Примеры

```bash
export RIMSORT_STEAM_API_KEY=your_32_character_key_here
RimSort build-db --output steamDB.json

RimSort build-db --output steamDB.json --no-dlc-data --quiet

RimSort build-db --output steamDB.json --update
```

#### Опции

| Опция | Тип | По умолчанию | Описание |
|--------|------|---------|-------------|
| `--api-key TEXT` | String | (см. ниже) | WebAPI ключ или `RIMSORT_STEAM_API_KEY` |
| `--output PATH` | Path | **обязательно** | Путь к JSON |
| `--dlc-data/--no-dlc-data` | Boolean | dlc-data | DLC через Steamworks (медленнее) |
| `--update/--overwrite` | Boolean | overwrite | Обновить или перезаписать |
| `--quiet` | Flag | false | Без прогресса в stdout |

#### Ключ API

1. `--api-key` — высший приоритет (история shell)
2. `RIMSORT_STEAM_API_KEY` — рекомендуется
3. `settings.json` из GUI

#### Коды выхода

- **0** — успех
- **1** — ошибка
- **2** — Ctrl+C

### Устранение проблем

##### **`Error: Steam API key is required`**

Укажите ключ: `--api-key`, `RIMSORT_STEAM_API_KEY` или в GUI.

##### **`Error: Invalid Steam WebAPI key! Key must be 32 characters`**

Проверьте длину на [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).

##### **`Error: Cannot update non-existent database`**

Первый запуск — `--overwrite` (по умолчанию):

```bash
RimSort build-db --output steamDB.json --overwrite
RimSort build-db --output steamDB.json --update
```

##### **DLC не собирается**

Нужны Steam + RimWorld. Headless: `--no-dlc-data`.

```bash
RimSort build-db --output steamDB.json --no-dlc-data
```
