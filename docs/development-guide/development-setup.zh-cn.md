---
title: 开发配置和构建
nav_order: 1
layout: default
parent: 开发指南
permalink: development-guide/development-setup
lang: zh-cn
---
# 开发配置和构建

{: .no_toc }

## 目录

{: .no_toc .text-delta }

1. TOC
{:toc}

### 简介

RimSort 使用 Python 编写，基于 [PySide6](https://pypi.org/project/PySide6/) 模块，此外还使用其他多个模块。部分模块在构建时需要特别处理。最终使用 [Nuitka](https://nuitka.net/) 编译打包。

## 前置条件

### 操作系统

RimSort 目前支持 Windows、macOS 和 Linux，不过我们目前仅为 Ubuntu 制作构建产物。它可能在其他 Linux 发行版上也能运行，但 Ubuntu 是我们的基线。

您的操作系统必须是 PySide6 所支持的。例如，我们使用以下 GitHub runner 制作发布构建：

- Linux：
  - `ubuntu-22.04`
  - `ubuntu-24.04`
- macOS 构建：
  - `macos-15-intel`（x86_64）
  - `macos-latest`（arm）
- Windows：
  - `windows-latest`

### 工具和软件

**必需：**

- [git](https://git-scm.com/)
- [Python](https://python.org/) 3.12（如需，可通过 uv 安装）
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [just](https://just.systems/man/en/installation.html) — 用于开发命令的任务运行器

**用于代码质量检查**（由 `just check` 和 CI 使用）：

- [Node.js / npx](https://nodejs.org/) — 用于 [JSCPD](https://github.com/kucherenko/jscpd) 复制粘贴检测（`just jscpd`）
- [shfmt](https://github.com/mvdan/sh#shfmt) — shell 脚本格式化工具（`just shfmt`）

Python 代码检查工具（ruff、mypy）由 `uv sync` 自动安装 — 无需手动设置。

### 克隆仓库

RimSort 使用托管在其他仓库中的子模块，需要同步克隆。

- [steamfiles](https://github.com/RimSort/steamfiles)：用于解析 Steam 客户端的 acf/appinfo/manifest 信息
- [SteamworksPy](https://github.com/philippj/SteamworksPy)：用于与本地 Steam 客户端交互
  - SteamworksPy 是直接对接 [Steamworks API](https://partner.steamgames.com/doc/api) 的 Python 模块
  - 这使得可以通过 Python 经由 Steamworks API 发起与本地 Steam 客户端的交互（例如通过 RimSort 订阅/取消订阅 Steam 工坊 Mod）

带子模块克隆：

```shell
git clone --recurse-submodules -j8 https://github.com/RimSort/RimSort
```

如需更新这些子模块，或忘记使用 `--recurse-submodules` 克隆，请运行：

```shell
git submodule update --init --recursive
```

## 配置环境

RimSort 使用 Python 包与项目管理器 [uv](https://docs.astral.sh/uv/)。

配置全部内容（子模块、venv、开发及构建依赖）最简单的方式是：

```shell
just dev-setup
```

该命令会运行 `uv sync --locked --dev --group build`，安装所有运行时、开发及构建依赖（包括 ruff 和 mypy 等代码检查工具）。

配置完成后，安装共享 git hooks，使每次提交前自动运行 `just check`：

```shell
just install-hooks
```

如果您更倾向于手动配置：

```shell
uv sync --dev            # 安装运行时 + 开发依赖（代码检查工具、测试工具等）
uv sync --group build    # 额外安装构建依赖（nuitka 等）
```

## 自动构建流程

- 若要（基本全自动地）构建 RimSort，请执行提供的脚本：
  - 运行 `uv run python distribute.py`
    - 该命令会为您的平台构建 RimSort 并输出构建产物（包含所有依赖和子模块）
    - 如需禁用某些步骤等额外选项，参见 `uv run python distribute.py --help`

## 手动构建

确保已通过运行 `uv sync --group build` 安装构建依赖。

### 配置附加依赖项

RimSort 使用 Python，并依赖多个 Python 模块。您可以通过 `pyproject.toml` 安装/查看上述大部分依赖项。这些依赖会在前面「配置环境」的步骤中安装。不过，**SteamworksPy** 是一个特例，需要特别处理。

有关如何配置它们，请参阅各自对应的章节。或者使用 `distribute.py` 自动完成。默认情况下该脚本会构建 RimSort，但可以通过参数启用/禁用包括构建在内的各种步骤。更多信息参见 `uv run python distribute.py --help`。

- Mac 用户还应注意，Apple 有自己的运行时保护机制 [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
  - 这可能导致运行 RimSort（或执行相关依赖库）时出现问题！
  - 可以通过 `xattr` 命令手动加入白名单：
    - `xattr -d com.apple.quarantine /path/to/RimSort.app`
    - `xattr -d com.apple.quarantine /path/to/libsteam_api.dylib`
  - 将 `/path/to/` 替换为文件/文件夹的实际路径，例如：
    - `xattr -d com.apple.quarantine /Users/John/Downloads/RimSort.app`

### 使用 SteamworksPy 二进制文件

要让 RimSort 实际使用 SteamworksPy 模块，您需要为您的平台准备编译好的库文件，以及 steamworks SDK 的二进制文件，并放置在 RimSort 项目根目录下，配合子模块 `submodules/SteamworksPy/library` 所包含的 Python 模块一起使用。

- 仓库维护者会为 `SteamworksPy` 库提供预编译的二进制文件，steamworks-sdk 的 redistributables 也会随仓库以及每个平台的发布版本一并提供。
- 在 Linux 上，您需要将 `SteamworksPy_*.so`（其中 \* 代表您的 CPU 架构）复制为 `SteamworksPy.so`
- 在 macOS 上，您需要将 `SteamworksPy_*.dylib`（其中 \* 代表您的 CPU 架构）复制为 `SteamworksPy.dylib`

### 从源码构建 SteamworksPy

{: .note}
> 撰写本文时，SteamworksPy 模块只能使用 Python 11 构建，与 RimSort 本身不同。您可能需要使用与处理 RimSort 所用的不同 Python 环境。

- 可以通过以下命令配置该模块：

  - `cd SteamworksPy`
  - `pip install -r requirements.txt`

这是 _**可选**_ 步骤。您 _**无需**_ 执行此操作——仓库中已提供预编译的二进制文件，各平台的发布版本中也已包含。未经维护者同意，请勿尝试提交/发起更新这些二进制文件的 PR——此类请求将不予批准。

参考文档：[SteamworksPy](https://philippj.github.io/SteamworksPy/)

- 在 Linux 上，您需要 `g++`。我在 Ubuntu 上无需额外配置即可使用。
- 在 macOS 上，您需要 Xcode 命令行工具。之后可直接通过脚本编译（无需完整安装 Xcode）：
- 在 Windows 上，您需要 Visual Studio 和 Visual Studio 构建工具：
  - [MSVC](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
    - 运行下载的程序时，会更新并启动 Visual Studio Installer。如需仅安装 C++ 开发所需工具，请选择「使用 C++ 的桌面开发」工作负荷。或者直接安装带标准工具集的 VS Community 2022。

执行：`python -c "from distribute import build_steamworkspy; build_steamworkspy()"`

### 纹理优化（todds）

- RimSort 使用 [todds](https://github.com/todds-encoder/todds) 作为纹理优化的依赖项。该工具已随 RimSort 发布版本集成、打包进二进制发行版中。如果您从源码构建/运行，需要将 todds 二进制文件放置在 `./todds/todds`（Linux/Mac）或 `.\todds\todds.exe`（Windows）。

### 从源码运行 RimSort

1. 将本仓库（含子模块）克隆到本地目录。
2. 确保已完成上述所有前置步骤。
3. 在项目根目录执行 `uv run python -m app`

### 开发模式数据隔离

RimSort 支持一种**开发模式（dev mode）**，它会将所有用户数据（设置、日志、数据库、Mod 列表、主题、备份）重定向到仓库根目录下的 `dev/` 子目录，而不是您平台的应用程序数据目录。这可以防止开发运行时破坏您的生产环境 RimSort 配置。

启用开发模式，请传入 `--dev` 参数：

```shell
uv run python -m app --dev
```

**开发模式下的变化：**

- 设置存储于 `dev/data/settings.json`
- 日志写入 `dev/logs/`
- 数据库、Mod 列表和备份位于 `dev/data/` 下
- 默认启用调试级别日志
- 窗口标题会带有 `[DEV]` 后缀

**环境变量覆盖：**

| 变量 | 取值 | 作用 |
| :--- | :--- | :--- |
| `RIMSORT_DEV` | `1`、`true` | 强制开启开发模式（等价于 `--dev`） |
| `RIMSORT_DEV` | `0`、`false` | 强制关闭开发模式（覆盖 `--dev`） |
| `RIMSORT_DEV_DIR` | 绝对路径 | 覆盖开发数据根目录（仅当开发模式启用时） |

使用自定义开发数据目录：

```shell
RIMSORT_DEV_DIR=/tmp/rimsort-test uv run python -m app --dev
```

或仅通过环境变量：

```shell
RIMSORT_DEV=1 RIMSORT_DEV_DIR=/tmp/rimsort-test uv run python -m app
```

`dev/` 目录在 `.gitignore` 中，不会被提交。

### 打包 RimSort

打包可分发的 RimSort 二进制完全由 `distribute.py` 自动化：它会初始化子模块，（可选地）构建 SteamworksPy 库，获取最新版本的 `todds` 发行版，并使用 Nuitka 编译应用。在项目根目录运行：

```shell
uv run python distribute.py
```

如需额外选项（跳过分步、提供自定义 Steamworks SDK 源、启用开发模式等），参见：

```shell
uv run python distribute.py --help
```

如果需要直接驱动 Nuitka（例如本地迭代），请注意 `distribute.py` 中的 `freeze_application()` 会首先将 `SteamworksPy` 子模块添加到 `PYTHONPATH`，然后编译 `app/` 包。真实构建请优先使用 `distribute.py` 脚本，而不是手动调用 Nuitka。
