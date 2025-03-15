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

## 使用创意工坊浏览器

## 更新 SteamCMD Mod

## SteamCMD 故障排查

{: .important}
> SteamCMD 作为外部工具，拥有独立的日志。你可以在 SteamCMD 安装目录中找到日志文件，具体路径取决于你的 RimSort 配置。
>
> 你可以在设置面板的 `SteamCMD > SteamCMD 安装位置（SteamCMD > SteamCMD installation location）` 查看当前 SteamCMD 安装位置。日志文件位于 `SteamCMD` 安装目录的 `logs` 子文件夹中。

有时，SteamCMD 可能出现下载失败，重新安装已删除 Mod 等异常行为。假如问题并非网络连接导致（即你的计算机可以正常访问 Valve 服务器），可尝试以下步骤：

 - 清除 SteamCMD 的 depot 缓存
 - 清除 .acf 文件

 自 `v1.0.11` 版本起，上述操作均可通过 RimSort 设置面板的 `SteamCMD` 选项卡完成，你也可手动执行。

 {: .warning}
 > RimSort 目前依赖 .acf 文件中的数据来检查 SteamCMD Mod 的更新。删除或清空 .acf 文件可能导致 Mod 更新功能异常。

[SteamCMD]: https://developer.valvesoftware.com/wiki/SteamCMD
