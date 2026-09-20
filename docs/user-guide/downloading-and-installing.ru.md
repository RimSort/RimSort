---
title: Загрузка и установка
parent: Руководство пользователя
nav_order: 1
permalink: user-guide/downloading-and-installing
lang: ru
---

# Загрузка и установка

{: .no_toc}

{: .warning }

> Большинству пользователей следует использовать [готовые релизы](https://github.com/RimSort/RimSort/releases), а **_не_** скачивать код репозитория через `Code > Download ZIP`. Эта опция скачивает исходный код, который не скомпилирован. Исходный код нужен только если вы планируете вносить вклад, собирать RimSort самостоятельно или запускать RimSort через интерпретатор Python.

Есть два типа релизов RimSort: stable (стабильные) и edge (передовые). Edge-релизы выходят намного чаще, но в них с большей вероятностью есть баги.

При скачивании релиза выбирайте файл, который больше подходит под вашу операционную систему, архитектуру CPU и потребности. Инструкции по запуску могут отличаться в зависимости от платформы.

[Стабильный релиз][Stable Release]{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[Edge-релиз][Edge Release]{: .btn .fs-5 .mb-4 .mb-md-0 }

## Содержание

{: .no_toc .text-delta }

1. TOC
{:toc}

## Windows

{: .d-inline-block}

Windows
{: .label .label-blue }

{: .important }
> В Windows исполняемый файл RimSort.exe иногда ошибочно помечается антивирусом, например Windows Defender, и удаляется.
>
> К сожалению, это побочный эффект использования [Nuitka](https://nuitka.net/) для компиляции Python-программы в легко распространяемый исполняемый файл без подписи. Подпись релиза стоит значительных денег и является регулярным расходом, что для нас нереально. Вам безопасно переопределить настройки антивируса и разрешить RimSort. Если сомневаетесь, просканируйте исполняемый файл через [Virus Total](https://www.virustotal.com/gui/) — он покажет мнение множества антивирусов, а дальше вы уже решите сами.

- Скачайте и распакуйте релиз `Windows x86-64`
- Запустите исполняемый файл: `RimSort.exe`

![](../assets/images/previews/windows_preview.png)

## macOS

{: .d-inline-block}

macOS
{: .label .label-red }

{: .important }
> Вы можете получить ошибку о том, что RimSort «повреждён» (damaged) от Gatekeeper.
> У Apple есть собственная защита времени выполнения — [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web). Она может вызывать проблемы при запуске RimSort (или при выполнении зависимых библиотек)!
> Обойти это можно, вручную добавив файлы в белый список с помощью команды `xattr`:
>
>     xattr -d com.apple.quarantine /path/to/RimSort.app
>     xattr -d com.apple.quarantine /path/to/libsteam_api.dylib
>
> Замените `/path/to/` на реальный путь, где находится файл/папка, например:
>
>     xattr -d com.apple.quarantine /Users/John/Downloads/RimSort.app
>
> Если вы по какой-то причине пытаетесь запустить сборку `x86_64` на Apple silicon, не включайте watchdog при запуске через Rosetta

{: .note }

> Инструмент текстур todds на текущий момент (по состоянию на май 2023) не поддерживает Apple silicon (Mac M1/M2 ARM64 CPU).

- Скачайте и распакуйте релиз Darwin/macOS, соответствующий вашей архитектуре CPU (ARM64 для Apple Silicon, x86_64 для Intel)
- С помощью `xattr` обойдите [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web) и добавьте `RimSort.app` и `libsteam_api.dylib` в белый список
- Откройте бандл приложения: `RimSort.app`

<img alt="Macpreview" src="https://github.com/RimSort/RimSort/assets/28567881/7731911b-cc7c-47c8-9c34-6f925fc5b188">

## Linux

{: .d-inline-block}

Linux
{: .label .label-yellow}

### AppImage (рекомендуется)

Самый простой способ запустить RimSort в Linux — AppImage. Он содержит все зависимости и работает на большинстве дистрибутивов без установки чего-либо.

1. Скачайте файл `.AppImage` со [страницы релизов][Releases]
2. Сделайте его исполняемым и запустите:

```shell
chmod +x RimSort-*.AppImage
./RimSort-*.AppImage
```

{: .note }
> Для работы AppImage требуется FUSE2. Большинство дистрибутивов его уже включает, но если вы получили ошибку, связанную с FUSE, установите `fuse2` / `libfuse2` из вашего пакетного менеджера или запустите с флагом `--appimage-extract-and-run` как обходное решение.

**Интеграция с рабочим столом:** для автоматической интеграции в меню приложений и простого обновления рассмотрите [AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher). Он регистрирует AppImage в вашем рабочем окружении, чтобы они появлялись в меню приложений и запускались как обычные установленные программы.

**Самообновление:** при запуске в виде AppImage встроенный обновлятор RimSort заменяет файл AppImage на месте (старая версия сохраняется в `.bak` и очищается при следующем запуске).

### Ubuntu Tarball

Предварительно собранные tarball-релизы компилируются на Ubuntu 22.04 и 24.04. Они могут работать и на других дистрибутивах на основе Debian или на дистрибутивах с совместимыми версиями glibc и библиотек, но это не гарантируется.

1. Скачайте и распакуйте релиз `.tar.gz` (или `.zip`) для Ubuntu, соответствующий вашей версии Ubuntu
2. Запустите исполняемый файл:

```shell
./RimSort
```

{: .important }
> Если ни один из предварительно собранных релизов не работает для вашего дистрибутива, вы можете [собрать RimSort из исходников или запустить его через интерпретатор Python](../development-guide/development-setup).

<img alt="Linuxpreview" src="https://github.com/RimSort/RimSort/assets/102756485/d26577e4-d488-406b-b9a2-dc2eeea8de25">

### Зависимости Qt

RimSort использует Qt (PySide6) для своего GUI. Если вы используете tarball-релиз (не AppImage), в вашей системе могут отсутствовать требуемые разделяемые библиотеки Qt. Самая распространённая отсутствующая библиотека — `libxcb-cursor`.

**Debian / Ubuntu:**

```shell
sudo apt install libxcb-cursor0
```

Если вы получили ошибки о других отсутствующих библиотеках, используйте `apt-file`, чтобы найти пакет:

```shell
sudo apt install apt-file
apt-file update
apt-file search libxcb-whatever.so
```

**Fedora / RHEL:**

```shell
sudo dnf install xcb-util-cursor
```

Для поиска пакетов для других отсутствующих библиотек используйте `dnf provides`:

```shell
dnf provides '*/libxcb-whatever.so*'
```

**Arch / Manjaro:**

```shell
sudo pacman -S xcb-util-cursor
```

Для поиска отсутствующих библиотек используйте `pkgfile`:

```shell
pkgfile libxcb-whatever.so
```

### Пути RimWorld в Linux

RimSort нужно знать, куда установлен RimWorld и где хранится его конфигурация. Пути различаются в зависимости от того, как установлены Steam и RimWorld.

{: .important }
> **Нативный Steam (из пакетного менеджера вашего дистрибутива) и нативная linux-версия RimWorld — предпочтительный и рекомендуемый способ установки.** Запуск RimWorld через его нативную Linux-сборку обеспечивает наилучшую совместимость с RimSort.

#### Нативный Steam (рекомендуется)

| Путь | Расположение |
|------|------|
| Установка игры | `~/.local/share/Steam/steamapps/common/RimWorld/` |
| Папка конфигурации | `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config/` |
| Моды из мастерской | `~/.local/share/Steam/steamapps/workshop/content/294100/` |
| Сохранения | `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Saves/` |

Если у вас библиотеки Steam на других дисках, пути к игре и мастерской будут находиться в каталоге `steamapps/` этой библиотеки.

#### Flatpak Steam

Если вы установили Steam через Flatpak, все пути изолированы под `~/.var/app/com.valvesoftware.Steam/`:

| Путь | Расположение |
|------|------|
| Установка игры | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/RimWorld/` |
| Папка конфигурации | `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config/` |
| Моды из мастерской | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/workshop/content/294100/` |

{: .warning }
> **Snap Steam не рекомендуется и не поддерживается.** Snap-пакет Steam имеет известные проблемы с совместимостью игр и официально не поддерживается Valve. Вместо него используйте нативный `.deb`-пакет или версию Flatpak.

#### Proton (Windows-версия RimWorld через Steam Play)

Если вы запускаете Windows-версию RimWorld через Proton вместо нативной Linux-сборки, папка конфигурации находится внутри виртуальной файловой системы Windows от Proton:

| Путь | Расположение |
|------|------|
| Папка конфигурации | `~/.local/share/Steam/steamapps/compatdata/294100/pfx/drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config/` |
| Сохранения | `~/.local/share/Steam/steamapps/compatdata/294100/pfx/drive_c/users/steamuser/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Saves/` |

Пути к установке игры и модам из мастерской остаются такими же, как у нативного Steam. Если вы используете Flatpak Steam с Proton, добавьте `~/.var/app/com.valvesoftware.Steam/` к пути compatdata, как указано выше.

{: .note }
> При запуске через Proton исполняемый файл RimWorld — это `RimWorldWin64.exe` (или `RimWorldWin.exe`), а не `RimWorldLinux`. RimSort определяет оба автоматически, но имейте это в виду, если задаёте пути вручную.

{: .note }
> Нативная Linux-сборка RimWorld предпочтительнее Proton. У неё проще пути и лучше совместимость с функциями RimSort.

### Расположение данных RimSort

RimSort хранит свои данные в подходящих для платформы каталогах (через `platformdirs`):

| Данные | Расположение |
|------|------|
| Данные приложения / настройки | `~/.local/share/RimSort/` |
| Логи | `~/.local/state/RimSort/log/RimSort.log` |

Чтобы включить отладочное логирование, создайте пустой файл с именем `DEBUG` в папке данных приложения:

```shell
touch ~/.local/share/RimSort/DEBUG
```

### Wayland vs X11

RimSort использует PySide6 (Qt6), который изначально поддерживает Wayland. В большинстве случаев он будет работать без дополнительной настройки.

Если на Wayland возникают проблемы с отрисовкой или падения, вы можете принудительно включить режим X11 через XWayland:

```shell
QT_QPA_PLATFORM=xcb ./RimSort
```

Или для AppImage:

```shell
QT_QPA_PLATFORM=xcb ./RimSort-*.AppImage
```

### Устранение неполадок

**Несовпадение версии glibc:**
Предварительно собранные tarball-релизы слинкованы с glibc из Ubuntu. Если в вашем дистрибутиве более старая glibc, вы можете увидеть ошибки вида `GLIBC_2.xx not found`. Используйте AppImage или [соберите из источников](../development-guide/development-setup).

**AppImage не запускается (ошибка FUSE):**
Установите `fuse2` или `libfuse2` из вашего пакетного менеджера. Либо запустите с `--appimage-extract-and-run`, чтобы обойти требование FUSE.

**Не работает самообновление AppImage:**
AppImage должен находиться в месте, доступном пользователю для записи. Если вы положили его туда, где нужны права root (например, `/opt/`), либо переместите его в домашний каталог, либо обновите его вручную.

**Не работает интеграция со Steam:**
Перед запуском RimSort убедитесь, что Steam запущен. Steamworks API требует активного подключения к клиенту Steam. Если вы используете Flatpak Steam, RimSort (запущенный вне песочницы) может не суметь с ним связаться — рекомендуется нативный Steam.

**Не определяются пути к модам:**
Если RimSort не находит ваши моды или конфигурацию, перепроверьте, какой способ установки Steam вы используете (нативный, Flatpak или Snap), и задайте пути вручную в настройках RimSort. См. [таблицы путей выше](#пути-rimworld-в-linux).

**Последнее средство — запуск из исходников:**
Если ни один из предварительно собранных релизов не работает для вашей системы, вы всегда можете запустить RimSort прямо из исходников Python. Инструкции см. в [руководстве по разработке](../development-guide/development-setup).

[Releases]: https://github.com/RimSort/RimSort/releases
[Stable Release]: https://github.com/RimSort/RimSort/releases/latest
[Edge Release]: https://github.com/RimSort/RimSort/releases/tag/Edge
