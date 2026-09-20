---
title: CLI 参考
nav_order: 8
layout: default
parent: 用户指南
permalink: user-guide/cli-reference
lang: zh-cn
---
# CLI 参考

{: .no_toc}

RimSort 提供命令行界面，用于以无头模式运行关键功能。这使你可以实现自动化工作流、CI/CD 集成以及编写脚本，而无需使用图形界面。

## 目录

{: .no_toc .text-delta }

1. TOC
{:toc}

## 概述

RimSort CLI 专为需要在无头环境中自动化 RimSort 功能的用户设计。与图形界面不同，CLI：

- **无需显示服务器** — 非常适合 Docker 容器、远程服务器和 CI/CD 流水线
- **提供结构化的退出代码** — 可在脚本和自动化中实现可靠的错误处理
- **支持环境变量** — 安全配置凭据，而不会在命令历史中泄露
- **不启动 GUI** — 无头运行，不会打开任何窗口（代码库仍会导入 PySide6，但不会实例化图形界面）

目前可用的命令：

- `build-db` - 构建 Steam Workshop 元数据库

未来版本可能会添加更多命令，以支持更多 RimSort 功能。

## 运行 CLI

如果你通过发行版安装 RimSort：

```bash
./RimSort build-db --help
```

或使用 Windows：

```bash
RimSort.exe build-db --help
```

如果从源代码运行：

```bash
python -m app build-db --help

# 或者使用 uv：
uv run python -m app build-db --help
```

## 命令

### `build-db`

通过查询 Steam WebAPI 构建 Steam Workshop 元数据库。生成的数据库包含模组名称、URL、依赖项以及可选的 DLC 需求，JSON 格式与 RimSort 和 RimPy 兼容。

#### 先决条件

**Steam WebAPI 密钥**
{: .d-inline-block}
必需
{: .label .label-red }

{: .important }
关于如何获取 Steam WebAPI 密钥的详细说明，请参阅 [数据库构建器指南](db-builder#如何获取-steam-webapi-密钥用于数据库构建器)。

{: .warning}
要使用此功能，你需要在 Steam 上拥有 RimWorld。你可能还需要在 Steam 账户上消费至少 5 美元，才能获得 Steam WebAPI 的一般访问权限，以便利用 Steamworks API（用于 DLC 依赖数据）。

要使用此命令，你需要一个 Steam WebAPI 密钥（32 个字符）。数据库构建器还有一些继承自 Steam API 访问策略的「隐性要求」：

#### 基本用法

```bash
# 使用环境变量（出于安全考虑推荐）
export RIMSORT_STEAM_API_KEY=your_32_character_key_here
RimSort build-db --output steamDB.json

# 不包含 DLC 数据的快速构建（更快）
RimSort build-db --output steamDB.json --no-dlc-data --quiet

# 更新现有数据库而不是覆盖
RimSort build-db --output steamDB.json --update
```

#### 选项参考

| 选项 | 类型 | 默认值 | 说明 |
|--------|------|---------|-------------|
| `--api-key TEXT` | String | （见下文） | Steam WebAPI 密钥（32 个字符）。也可以通过 `RIMSORT_STEAM_API_KEY` 环境变量设置。 |
| `--output PATH` | Path | **必需** | 数据库输出 JSON 文件路径。 |
| `--dlc-data/--no-dlc-data` | Boolean | dlc-data | 通过 Steamworks API 包含 DLC 依赖数据。需要运行中的 Steam 客户端和 RimWorld 拥有权。由于额外的 API 调用，速度会显著变慢。 |
| `--update/--overwrite` | Boolean | overwrite | 更新现有数据库（合并新数据）或完全覆盖。 |
| `--quiet` | Flag | false | 抑制进度输出。错误仍会写入 stderr。 |

#### 环境变量与配置

Steam API 密钥可以通过三种方式提供，优先级如下：

1. **`--api-key` 命令行参数** - 优先级最高，但可能将密钥暴露在 shell 历史中
2. **`RIMSORT_STEAM_API_KEY` 环境变量** - 出于安全考虑推荐
3. **回退到 `settings.json`** - 如果你已经配置过 RimSort GUI，CLI 将使用该 API 密钥

#### 退出代码

`build-db` 命令使用标准退出代码，便于自动化：

- **0** - 成功：数据库已成功构建/更新
- **1** - 错误：验证失败、构建失败或发生异常
- **2** - 中断：用户通过 Ctrl+C 取消

### 故障排查

##### **`Error: Steam API key is required`**

命令找不到有效的 API 密钥。请通过以下方式提供：

- `--api-key` 命令行选项
- `RIMSORT_STEAM_API_KEY` 环境变量
- 在 RimSort GUI 中配置（保存到 `settings.json`）

##### **`Error: Invalid Steam WebAPI key! Key must be 32 characters`**

你的 API 密钥长度不正确（错误信息也会显示收到的长度，例如 `(got 20)`）。请访问 [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) 检查你的密钥。常见问题：复制密钥时包含多余的空格或换行。

##### **`Error: Cannot update non-existent database`**

你使用了 `--update` 模式，但目标数据库文件不存在。首次构建请使用 `--overwrite`（默认值）：

```bash
# 首次构建
RimSort build-db --output steamDB.json --overwrite

# 后续更新
RimSort build-db --output steamDB.json --update
```

##### **`DLC 数据收集静默失败`**

DLC 依赖数据需要 Steamworks API，这需要：

- 运行中且已认证的 Steam 客户端
- 你的 Steam 账户拥有 RimWorld

如果不可用，请在无头环境中使用 `--no-dlc-data`：

```bash
RimSort build-db --output steamDB.json --no-dlc-data
```
