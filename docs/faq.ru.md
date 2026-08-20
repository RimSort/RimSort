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

## Где настраиваются пути к игре?

В **Settings → Locations**.

## Что такое todds?

[todds](https://github.com/todds-encoder/todds) кодирует текстуры RimWorld в `.dds` для экономии памяти.

## Зачем Steam Workshop Database?

Steam DB даёт зависимости из мастерской, которых может не быть в `About.xml`. Подробнее — [базы данных](/ru/user-guide/databases).

## Зачем Community Rules Database?

CR DB задаёт порядок загрузки модов по правилам сообщества.

## Как включить интеграцию со Steam-клиентом?

**Settings → Advanced → Enable Steam client integration**.

## Ошибка `Could not initialize Steam API` при запуске игры

Убедитесь, что Steam запущен и интеграция включена. На macOS известная проблема — запускайте RimWorld через Steam; список модов из RimSort сохраняется в `ModsConfig.xml`.
