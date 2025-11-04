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

## 简介

RimSort 使用 [PySide6](https://pypi.org/project/PySide6/) 模块以及多个其他 Python 模块构建，部分模块需要特殊处理才能正确被编译。最终，使用 [Nuikta](https://nuitka.net/) 进行打包。

## 克隆仓库

- RimSort 使用了 Git 子模块，代码托管在其他仓库，需同步克隆：
- 带子模块克隆：`git clone --recurse-submodules -j8 https://github.com/RimSort/RimSort`

## 自动构建流程

- 前置条件：
  - 运行 PySide6 支持的操作系统
    - 最低要求示例：
      - Linux 构建：Ubuntu 22.04 和 24.04
      - macOS 构建：
        - i386 架构使用 GitHub 的 macos-14 runner
        - arm 架构使用 GitHub 的 macos-latest（当前为 macos-14）runner
      - Windows 使用 GitHub 的 windows-latest（当前为 Windows 2022）runner
  - 安装对应平台的最新版 [Python](https://python.org/) 3.12（推荐 CPython）
- 要（基本全自动的）构建 RimSort，请执行对应脚本：
  - 执行脚本：`python distribute.py`
    - 该脚本会为当前平台生成完整构建（模块含所有依赖和子模块）
    - 查看高级选项：`python distribute.py --help`

## 手动构建

- 推荐在 Python 虚拟环境中进行操作：
  - 在项目根目录执行：
    - `python -m pip install virtualenv`
    - `python -m venv .`
    - 激活环境：
      - Unix (`*sh`)：`source bin/activate`
      - Windows (`powershell`)：`.\Scripts\Activate.ps1`
  - 确保安装构建依赖：`requirements_build.txt`
- RimSort 还依赖以下必需子模块（执行 `git submodule update --init --recursive` 来初始化/更新）：
  - [steamfiles](https://github.com/twstagg/steamfiles)：用于解析 Steam 客户端 acf/appinfo/manifest 文件
  - [SteamworksPy](https://github.com/philippj/SteamworksPy)：用于实现与本地 Steam 客户端的交互
    - SteamworksPy 是直接对接 [Steamworks API](https://partner.steamgames.com/doc/api) 的 Python 模块
    - 这使 RimSort 可以通过 Python 调用 Steamworks API，与本地 Steam 客户端进行交互（例如通过 RimSort 订阅/取消订阅 Steam Mod）

### 配置 Python 及依赖项

- RimSort 使用 Python 开发，需要多个 Python 模块支持。你可以通过 `requirements.txt` 文件安装/查看大部分依赖项。在项目根目录执行以下命令可一次性安装所有依赖：

  - `pip install -r requirements.txt`
  - 注意：`requirements.txt` 并未包含部分依赖（如 steamfiles）。这些依赖以子模块形式存在于仓库中，需要手动本地安装
    - 若使用 `distribute.py` 脚本，该过程将自动完成

- **steamfiles** 和 **SteamworksPy** 依赖因特殊原因无法通过 requirements.txt 直接安装

  - 参阅各自章节了解配置方法，或使用 `distribute.py` 自动安装。默认情况下该脚本会直接构建 RimSort，但可通过参数配置启用/禁用构建等步骤。使用 `python distribute.py --help` 查看详细说明

- 使用 Apple M1/M2 芯片的 Mac 用户，若希望使用 MacPorts 而非 Homebrew，可参考以下命令配置：（同样适用于 i386 架构）

  - `sudo port select --set pip3 pip39`
  - `sudo port select --set python python9`

- Mac 用户需注意 Apple 的运行时保护机制 [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
  - 可能导致运行 RimSort 或相关依赖库时出现问题！
  - 可通过 `xattr` 命令手动添加白名单：
    - `xattr -d com.apple.quarantine /path/to/RimSort.app`
    - `xattr -d com.apple.quarantine /path/to/libsteam_api.dylib`
  - 将 `/path/to/` 替换为实际路径，例如：
    - `xattr -d com.apple.quarantine /Users/John/Downloads/RimSort.app`

### 配置 steamfiles 模块

- 通过运行 pip 安装命令来配置：
  - `pip install -e submodules/steamfiles`

### 使用 SteamworksPy 二进制文件

- 可以通过以下命令设置该模块：

  - `cd SteamworksPy`
  - `pip install -r requirements.txt`

- 要让 RimSort 实际使用 SteamworksPy 模块，你需要准备对应平台的编译库文件，以及 steamworks SDK 的二进制文件放置在 RimSort 项目根目录下，配合位于 `SteamworksPy/steamworks` 的 Python 模块使用。
  - 仓库维护者会为 `SteamworksPy` 库提供预编译的二进制文件，以及包含在仓库中的 steamworks-sdk 文件，在各平台的发布版本中也会附带这些文件。
  - 在 Linux 上，你需要将 `SteamworksPy_*.so`（其中 \* 代表你的 CPU 架构）复制为 `SteamworksPy.so`
  - 在 macOS 上，你需要将 `SteamworksPy_*.dylib`（其中 \* 代表你的 CPU 架构）复制为 `SteamworksPy.dylib`

### 从源码构建 SteamworksPy

这是 _**可选**_ 步骤。你 _**无需**_ 执行此操作——仓库中已提供预编译的二进制文件，各平台对应的发布版本中也已包含。未经维护者同意，请勿尝试提交/发起更新这些二进制文件的 PR 请求——此类请求将不予批准。

参考文档：[SteamworksPy](https://philippj.github.io/SteamworksPy/)

- 在 Linux 上，你需要安装 `g++`。Ubuntu 上可直接使用，无需额外配置。
- 在 macOS 上，你需要安装 Xcode 命令行工具。随后，可直接通过脚本编译（无需完整安装 Xcode）：
- 在 Windows 系统上，你需要安装 Visual Studio 和 Visual Studio 构建工具：
  - [MSVC](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
    - 运行下载的程序时，会更新并启动 Visual Studio 安装程序。若只需安装 C++ 开发相关工具，请选择「使用 C++ 的桌面开发」工作负荷，或者直接安装 VS Community 2022 的标准工具集

执行：`python -c "from distribute import build_steamworkspy; build_steamworkspy()"`

### 纹理优化（todds）

- RimSort 使用 [todds](https://github.com/joseasoler/todds) 作为纹理优化的依赖项。该工具已随 RimSort 发布版本打包。如果你从源码构建/运行 RimSort，需要将 todds 的二进制文件放置在以下路径：
  - Linux/Mac：`./todds/todds`
  - Windows：`.\todds\todds.exe`

### 从源码运行 RimSort

1. 将本仓库克隆到本地（需包含子模块）
2. 确保已完成上述所有前提步骤
3. 在项目根目录执行：`python -m app`

### 打包 RimSort

1. 首先将本仓库克隆到本地目录
2. 使用 `nuitka` 打包：
   - 完成前置环境配置后，运行 `python distribute.py`
   - 或参考该脚本中各平台使用的具体命令
