---
title: Частые вопросы
nav_order: 2
description: "Частые вопросы"
layout: default
permalink: faq/
lang: ru
---

# Частые вопросы

## macOS Gatekeeper / Windows Defender считает RimSort опасным

RimSort не вредоносен. Сборки на Python/Nuitka часто дают ложные срабатывания AV. Можно добавить исключение или проверить файл на VirusTotal.

На Windows мы по возможности отправляем релизы Microsoft на whitelist — процесс занимает время и повторяется каждый релиз.

На macOS нужна платная подпись Apple; временный обход — [инструкция по установке](/ru/user-guide/downloading-and-installing#macos).

## Как вручную обновить RimSort, если встроенный обновлятор не сработал?

Закройте RimSort и скачайте последний релиз, соответствующий вашему типу (stable или edge), операционной системе и архитектуре CPU, со [страницы релизов RimSort](https://github.com/RimSort/RimSort/releases). Не используйте `Code > Download ZIP` — этот архив содержит исходный код, а не готовую сборку. Распаковывайте архивные релизы в новую пустую папку, а не поверх старой установки; на macOS замените существующий `RimSort.app`, а на Linux замените AppImage и сделайте новый файл исполняемым с помощью `chmod +x RimSort-*.AppImage`. Запустите новую версию, прежде чем удалять старые файлы приложения. Ваши настройки и прочие данные RimSort хранятся отдельно в каталоге данных приложения операционной системы — оставьте этот каталог на месте. Инструкции для каждой платформы см. в разделе [Загрузка и установка](/ru/user-guide/downloading-and-installing).

## Где настраиваются пути к игре?

В **Settings → Locations**.

## Что такое todds?

[todds](https://github.com/todds-encoder/todds) кодирует текстуры RimWorld в `.dds` для экономии памяти.

## Зачем Steam Workshop Database?

Steam DB даёт зависимости из мастерской, которых может не быть в `About.xml`. Подробнее — [базы данных](/ru/user-guide/databases).

## Зачем Community Rules Database?

CR DB задаёт порядок загрузки модов по правилам сообщества.

## Как включить интеграцию со Steam-клиентом?

**Settings → Locations → Enable Steam client integration**.

## Ошибка `Could not initialize Steam API` при запуске игры

Убедитесь, что Steam запущен и интеграция включена. На macOS известная проблема — запускайте RimWorld через Steam; список модов из RimSort сохраняется в `ModsConfig.xml`.
