---
title: SteamCMD 与创意工坊浏览器
nav_order: 5
parent: 用户指南
permalink: user-guide/steamcmd-browser
lang: zh-cn
---
# SteamCMD 与创意工坊浏览器

{: .no_toc}

[SteamCMD][SteamCMD] 是由 Valve 发布的工具，RimSort 可选地集成该工具，来实现无 Steam 客户端或 Steam 版 RimWorld 时下载 Steam 创意工坊 Mod。RimSort 内置的创意工坊浏览器允许你直接浏览 Steam 创意工坊，并通过 SteamCMD 下载选择的 Mod。

RimSort 支持通过 SteamCMD 安装的 Mod 的更新，这意味着比起直接使用 Steam 客户端，你可以更精细地控制 Steam 创意工坊 Mod 的更新时机。

## 目录

{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 配置 SteamCMD

在 Linux 上，RimSort 会将 SteamCMD 的用户配置保存在所配置的 SteamCMD 前缀目录内一个专用的 `home` 目录中。这可以防止 SteamCMD 修改桌面 Steam 客户端的库配置。

## 使用创意工坊浏览器

Steam 创意工坊浏览器是一个内嵌的 Steam Community 网页视图，让你无需离开 RimSort 即可浏览 RimWorld 创意工坊并将 Mod 加入下载队列。侧边栏（**Mod Downloader**）保存着你选择的 Mod 列表。

要添加 Mod：

1. 在浏览器中进入某个 Mod 或合集页面。当当前页面是 Mod 详情或合集页面时，导航栏会出现 **Add to list（添加到列表）** 按钮。
2. 点击 **Add to list** 将 Mod 追加到下载列表。你也可以点击 **Add Mods by Workshop ID（按创意工坊 ID 添加 Mod）** 直接粘贴一个或多个 Steam published file ID。

下载列表中的每个条目都会显示一个表示其状态的状态徽标：

- **Default（默认）** — Mod 已在列表中但尚未下载。此状态下列表显示 **Add to list** 控件。
- **Added（已添加）** — Mod 已被选中并进入队列。此状态以 `-` 徽标标记。
- **Installed（已安装）** — Mod 已存在于当前激活 Mod 集中。此状态以 `✓` 徽标标记。

右键点击条目可单独移除它，双击条目可打开其创意工坊页面，点击 **Clear List（清空列表）** 可清空整个队列。

列表准备好后，选择获取 Mod 的方式：

- **Download mod(s) (SteamCMD)** — 通过 SteamCMD 下载。这**不**需要 Steam 客户端或 Steam 版 RimWorld，是离线 / SteamCMD 实例的首选方式。
- **Download mod(s) (Steam app)** — 通过 Steam 客户端（Steamworks API）订阅。这需要 Steam 客户端正在运行且已登录，并且你在 Steam 拥有 RimWorld。当你希望 Mod 也由 Steam 库管理时，请使用此方式。

{: .note}
> 浏览时 RimSort 会隐藏 Steam 原生的「订阅」按钮，以便所有下载都通过上述两种方式完成。

## 更新 SteamCMD Mod

RimSort 通过 SteamCMD 前缀目录中的 `appworkshop_294100.acf` 文件跟踪你通过 SteamCMD 下载的 Mod。要检查更新，请使用 `下载 > 更新创意工坊 Mod（Download > Update Workshop Mods）`，或启用 *刷新时检查 Mod 更新（Check for mod updates on refresh）*（位于 *设置 → 高级（Settings → Advanced）*），以便每次刷新 Mod 列表时自动执行检查。

检查时，RimSort 会将已安装 SteamCMD Mod 的更新时间戳（`.acf` 文件中的 `timeupdated` 值和 Mod 文件夹的修改时间）与 Steam WebAPI 报告的最新时间戳进行比较。过时的 Mod 会出现在 *创意工坊 Mod 更新器（Workshop Mod Updater）* 面板中，你可以在其中通过 SteamCMD 重新下载它们，或再次通过 Steam 客户端（Steamworks API）订阅。

如果你希望在每次更新时都用干净的副本替换 Mod，请在 *设置 → 内部工具 → SteamCMD（Settings → Internal Tools → SteamCMD）* 下启用 **更新前删除（Delete before update）**。这会在重新下载前删除现有的 Mod 文件夹。请注意，由于 RimSort 依赖 `.acf` 文件进行更新检测，清空 `.acf` 文件可能会干扰更新检查 — 参见下面的 [SteamCMD 故障排查](#steamcmd-故障排查)。

## SteamCMD 故障排查

{: .important}
> SteamCMD 作为外部工具，拥有独立的日志。你可以在 SteamCMD 安装目录中找到日志文件，具体路径取决于你的 RimSort 配置。
>
> 你可以在设置面板的 `SteamCMD > SteamCMD 安装位置（SteamCMD > SteamCMD installation location）` 查看当前 SteamCMD 安装位置。日志文件位于 `SteamCMD` 安装目录的 `logs` 子文件夹中。

有时，SteamCMD 可能出现下载失败，重新安装已删除 Mod 等异常行为。假如问题并非网络连接导致（即你的计算机可以正常访问 Valve 服务器），可尝试以下步骤：

 - 清除 SteamCMD 的 depot 缓存
 - 清除 .acf 文件

 上述操作均可在 RimSort 设置面板的 `内部工具（Internal Tools） > SteamCMD` 中完成，你也可以手动执行。

 {: .warning}
 > RimSort 目前依赖 .acf 文件中的数据来检查 SteamCMD Mod 的更新。删除或清空 .acf 文件可能导致 Mod 更新功能异常。

[SteamCMD]: https://developer.valvesoftware.com/wiki/SteamCMD
