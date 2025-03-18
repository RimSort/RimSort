---
title: 下载和安装
parent: 用户指南
nav_order: 1
permalink: user-guide/downloading-and-installing
lang: zh-cn
---

# 下载和安装
{: .no_toc}

{: .warning }

> 大多数用户应当使用 [预构建版本](https://github.com/RimSort/RimSort/releases)，而**_不要_**通过 `Code > Download ZIP` 下载仓库代码。该选项下载的是未经编译的源代码，仅当您计划参与贡献，自行构建 RimSort，或使用 Python 解释器运行 RimSort 时才需要获取源代码。

RimSort 提供两种发行版本：稳定版（stable releases）和前瞻版（edge releases）。前瞻版的更新频率高于稳定版，但更可能存在 Bug。

下载时请根据操作系统、CPU 架构及实际需求选择对应文件。启动说明可能因平台而异。

[稳定版][稳定版]{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[前瞻版][前瞻版]{: .btn .fs-5 .mb-4 .mb-md-0 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

## Windows
{: .d-inline-block}

Windows
{: .label .label-blue }

{: .important }
> 在 Windows 上，RimSort.exe 有时可能会被您的反病毒软件（例如 Windows Defender）误判为威胁并删除。
>
> 这是使用 [Nuikta](https://nuitka.net/) 将 Python 程序编译为易于分发的可执行文件，且未进行数字签名所产生的副作用。为发布程序进行数字签名需要高昂且持续的费用，这对我们而言并不现实。您可以安全地配置反病毒软件，以允许 RimSort 运行。若对此存疑，建议使用 Virus Total 扫描该可执行文件，该平台会综合多家反病毒软件的检测结果供您参考判断。


- 下载并解压 `Windows x86-64` 版本
- 运行程序：`RimSort.exe`

![](../../assets/images/previews/windows_preview.png)

## macOS
{: .d-inline-block}

macOS
{: .label .label-red }

{: .important }
> 您可能会遇到 Gatekeeper 提示 RimSort 已「损坏」的错误。
> 苹果自有的运行时保护机制 [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web) 可能导致运行 RimSort（或执行相关依赖库）时出现问题！
> 可通过以下 `xattr` 命令手动添加白名单规避此问题：
>
>     xattr -d com.apple.quarantine /path/to/RimSort.app
>     xattr -d com.apple.quarantine /path/to/libsteam_api.dylib
>
> 将 `/path/to/` 替换为文件/文件夹的实际路径，例如：
>
>     xattr -d com.apple.quarantine /Users/John/Downloads/RimSort.app
>
> 如果因某些原因尝试在 Apple Silicon 芯片上运行 `i386` 架构版本，使用 Rosetta 运行时应禁用看门狗功能。

{: .note }

> 截至 2023 年 5 月，todds 纹理工具目前不支持 Apple Silicon 芯片（Mac M1/M2 ARM64 CPU）。

- 下载并解压与你的 CPU 架构匹配的 Darwin/macOS 版本（Apple Silicon 选择 ARM64，Intel 选择 i386）
- 使用 `xattr` 命令绕过 [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)，将 `RimSort.app` 和 `libsteam_api.dylib` 加入白名单
- 打开应用：`RimSort.app`

<img alt="Macpreview" src="https://github.com/RimSort/RimSort/assets/28567881/7731911b-cc7c-47c8-9c34-6f925fc5b188">

## Linux
{: .d-inline-block}

Linux
{: .label .label-yellow}

{: .warning }

> 某些 Linux 发行版可能缺少 RimSort 使用的图形库 QT 所需的部分共享库，比如 `xcb/libxcb`。如果在启动 RimSort 时遇到相关加载错误，你需要安装对应的库。即使安装了库，可能还需要单独下载一些缺失的文件。例如 `libxcb-cursor-dev`。
>
> 查找包含所需库软件包的最简单方法是使用 `apt-file` 命令。
>
> 内核版本不匹配可能导致共享库（如 `glibc`）出现版本错误。

{: .important }

> 我们目前仅提供适用于 Ubuntu 的预编译版本。如果你使用其他 Linux 发行版或特殊定制版本，可能会遇到预期外的问题。如果所有预构建版本都无法在你的系统上运行，你可能需要 [从源代码自行构建 RimSort 或通过 Python 解释器运行](/development-guide/development-setup)。



- 下载并解压适用于 Linux 的版本
- 运行可执行文件：`./RimSort`

<img alt="Linuxpreview" src="https://github.com/RimSort/RimSort/assets/102756485/d26577e4-d488-406b-b9a2-dc2eeea8de25">

[所有发布]: https://github.com/oceancabbage/RimSort/releases
[稳定版]: https://github.com/oceancabbage/RimSort/releases/latest
[前瞻版]: https://github.com/RimSort/RimSort/releases/tag/Edge
