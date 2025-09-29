---
layout: default
title: Translation Guidelines
nav_order: 4
parent: Development Guide
permalink: development-guide/translation-guidelines
---

# Translation Guide
{: .no_toc}

This guide explains how to contribute translations to RimSort. The project uses PySide6's Qt internationalization (i18n) system with QTranslator.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Translation System Overview

RimSort uses Qt's translation system with the following components:
- **`.ts` files**: Source translation files (XML format) that translators edit
- **`.qm` files**: Compiled binary translation files used by the application
- **QTranslator**: Qt's translation engine that loads and applies translations

## Project Structure

```
RimSort/
├── locales/           # Translation files directory
│   ├── en_US.ts      # English (source language)
│   ├── zh_CN.ts      # Simplified Chinese
│   ├── fr_FR.ts      # French
│   ├── de_DE.ts      # German
│   ├── es_ES.ts      # Spanish
│   ├── ja_JP.ts      # Japanese
│   ├── pt_BR.ts      # Portuguese (Brazil)
│   ├── ru_RU.ts      # Russian
│   └── tr_TR.ts      # Turkish
└── app/
    └── controllers/
        └── language_controller.py  # Language management
```

## Currently Supported Languages

| Language Code | Language Name | Status |
|---------------|---------------|--------|
| `en_US` | English | Complete (source) |
| `zh_CN` | 简体中文 (Simplified Chinese) | Complete |
| `fr_FR` | Français (French) | Complete |
| `de_DE` | Deutsch (German) | Complete |
| `es_ES` | Español (Spanish) | Complete |
| `ja_JP` | 日本語 (Japanese) | Complete |
| `pt_BR` | Português (Brasil) | Complete |
| `ru_RU` | Русский (Russian) | Complete |
| `tr_TR` | Türkçe (Turkish) | Complete |

## Translation Helper Tool

The project provides a comprehensive `translation_helper.py` script to assist with translation work.

**Important Note**: This tool is implemented using PySide6 commands and requires a properly configured development environment. Please refer to the [Development Setup Guide](development-setup.md) to set up your environment before using this tool.

### Available Commands

The translation helper tool provides the following commands:

#### Basic Commands
- **`check [language]`**: Check translation completeness for a specific language or all languages (if no language specified)
- **`stats`**: Show translation statistics for all languages
- **`validate [language]`**: Validate translation file format and content, automatically fixing common issues like placeholder mismatches
- **`update-ts [language]`**: Update .ts files with new strings from the source language
- **`compile [language]`**: Compile .ts files into binary .qm format

#### Advanced Commands
- **`auto-translate [language] --service [google|deepl|openai]`**: Auto-translate unfinished strings using various translation services
  - Supports Google Translate, DeepL, and OpenAI GPT models
  - Options: `--api-key` for service authentication, `--model` for OpenAI model selection, `--continue-on-failure` to skip failed translations
- **`process [language] --service [google|deepl|openai]`**: One-click workflow that runs update-ts → auto-translate → compile in sequence
  - Same options as auto-translate: `--api-key`, `--model`, `--continue-on-failure`

### Command Examples

```bash
# Check completeness for all languages
python translation_helper.py check

# Check specific language
python translation_helper.py check zh_CN

# View statistics for all languages
python translation_helper.py stats

# Validate and auto-fix all languages
python translation_helper.py validate

# Update translation files for all languages
python translation_helper.py update-ts

# Auto-translate using Google (free, no API key needed)
python translation_helper.py auto-translate zh_CN --service google

# Auto-translate using DeepL (requires API key)
python translation_helper.py auto-translate zh_CN --service deepl --api-key YOUR_DEEPL_KEY

# Auto-translate using OpenAI (requires API key)
python translation_helper.py auto-translate zh_CN --service openai --api-key YOUR_OPENAI_KEY --model gpt-4

# One-click complete workflow
python translation_helper.py process zh_CN --service google

# Compile all languages
python translation_helper.py compile
```

### Features

- **Batch Operations**: Most commands support operating on all languages when no specific language is provided
- **Auto-Fixing Validation**: The validate command automatically fixes placeholder and HTML tag mismatches
- **Multiple Translation Services**: Support for Google Translate (free), DeepL, and OpenAI with configurable models
- **Error Handling**: Robust error handling with retry logic and SSL fixes for Google Translate
- **Progress Tracking**: Real-time progress bars and detailed statistics
- **Caching**: Translation caching to avoid redundant API calls
- **Concurrency**: Optimized parallel processing for faster bulk operations

For specific usage methods, please refer to the "[Testing Your Translation](#step-5-testing-your-translation)" section.

## Quick Start

If you want to get started quickly with translation work, you can follow this simplified process:

1. **Fork and clone the project**
2. **Set up development environment** (following the [Development Setup Guide](development-setup.md))
3. **Choose language file**: Open `locales/YOUR_LANGUAGE.ts`
4. **Edit translations**: Find entries marked as `type="unfinished"` and translate them
5. **Auto-translate remaining strings** (optional): Run `python translation_helper.py auto-translate YOUR_LANGUAGE --service google`
6. **Compile and test**: Run `python translation_helper.py compile YOUR_LANGUAGE`
7. **Submit code**: Commit both `.ts` and `.qm` files

For detailed steps, please refer to the complete guide below.

## How to Contribute Translations

### Prerequisites

Before starting translation work, you need to prepare the following:

1. **Development Environment** (Required)
   - Set up the project development environment following the [Development Setup Guide](development-setup.md)
   - This includes installing Python 3.12, PySide6, and project dependencies

2. **Translation Editor**
   - **Recommended**: Text editor with XML syntax highlighting (VS Code, Sublime Text, Notepad++, etc.)
   - **Optional**: Qt Linguist (requires separate Qt development environment installation)

3. **Version Control Tools**
   - Git version control system
   - GitHub account for contributing code

### Step 1: Set Up Your Environment

1. Fork the RimSort repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/RimSort.git
   cd RimSort
   ```

3. Create a new branch for your translation:
   ```bash
   git checkout -b translation-LANGUAGE_CODE
   # Example: git checkout -b translation-pt_BR
   ```

### Step 2: Choose Your Contribution Type

#### Option A: Improve Existing Translation
{: .no_toc}

1. Navigate to the `locales/` directory
2. Open the existing `.ts` file for your language (e.g., `en_US.ts`)
3. Look for entries marked as `type="unfinished"` or empty `<translation>` tags

#### Option B: Create New Language Translation
{: .no_toc}

1. Use PySide6 tools to generate new translation file:

   **Linux/macOS systems**:
   ```bash
   pyside6-lupdate $(find app -name "*.py") -ts locales/NEW_LANGUAGE_CODE.ts -no-obsolete
   # Example:
   pyside6-lupdate $(find app -name "*.py") -ts locales/pt_BR.ts -no-obsolete
   ```

   **Windows systems (recommended to use translation helper tool)**:
   ```powershell
   # Use translation helper tool (recommended, simpler)
   python translation_helper.py update-ts pt_BR
   ```
   
   If you need to manually use PySide6 tools, you can refer to the Linux/macOS command format, but using the translation helper tool is recommended to avoid complex path handling.

2. Update the language attribute in the file:
   ```xml
   <TS version="2.1" language="pt_BR">
   ```

3. Register the new language in the language controller:
   
   Open the file `app/controllers/language_controller.py` and find the `language_map` dictionary in the `populate_languages_combobox` method, add your language:
   
   ```python
   language_map = {
       "en_US": "English",
       "es_ES": "Español", 
       "fr_FR": "Français",
       "de_DE": "Deutsch",
       "zh_CN": "简体中文",
       "ja_JP": "日本語",
       "pt_BR": "Português (Brasil)",  # Add new language entry
   }
   ```
   
   Where `"pt_BR"` is the language code and `"Português (Brasil)"` is the language name that will be displayed in the settings interface.

### Step 3: Translation Process

#### Using Text Editor (Recommended)
{: .no_toc}

1. Open the `.ts` file in your preferred text editor
2. Find `<message>` blocks that need translation:
   ```xml
   <message>
       <location filename="../app/views/settings_dialog.py" line="896"/>
       <source>Select Language (Restart required to apply changes)</source>
       <translation type="unfinished"></translation>
   </message>
   ```

3. Replace the empty translation with your text and remove `type="unfinished"`:
   ```xml
   <message>
       <location filename="../app/views/settings_dialog.py" line="896"/>
       <source>Select Language (Restart required to apply changes)</source>
       <translation>Selecionar Idioma (Reinicialização necessária para aplicar as alterações)</translation>
   </message>
   ```

#### Using Qt Linguist (Optional)
{: .no_toc}

If you already have Qt Linguist installed, you can also use it:

1. Open Qt Linguist
2. File → Open → Select your `.ts` file
3. Translate each string:
   - Select an untranslated item from the list
   - Enter your translation in the "Translation" field
   - Mark as "Done" when satisfied
   - Add translator comments if needed

4. Save your work: File → Save

### Step 4: Translation Guidelines

#### Context Understanding
{: .no_toc}

Each translatable string has context information:
- **Filename**: Shows which file contains the string
- **Line number**: Exact location in the source code
- **Context name**: Usually the class name (e.g., "SettingsDialog", "ModInfo")

#### Translation Best Practices
{: .no_toc}

1. **Preserve formatting**:
   - Keep `\n` for line breaks
   - Maintain `%s`, `%d`, `{0}`, `{variable_name}` placeholders
   - Preserve HTML tags if present

2. **UI considerations**:
   - Keep translations concise for button labels
   - Consider text expansion (some languages need more space)
   - Maintain the tone consistent with the application

3. **Technical terms handling principles**:
   - **"Mod"**: Keep as "Mod" in all languages (has become an internationally accepted term)
   - **"Workshop"**: Can be translated to localized terms or kept as original
   - **Software-specific terms**: Maintain consistency, recommend checking existing translations as reference
   - **UI element names**: Such as "Settings", "Options" should be translated to corresponding language
   - **File formats and extensions**: Such as ".ts", ".qm" should be kept as original

#### Example Translation
{: .no_toc}

```xml
<!-- English source -->
<source>Sort mods</source>
<translation>Ordenar mods</translation>

<!-- With placeholders -->
<source>Found {count} mods</source>
<translation>Encontrados {count} mods</translation>

<!-- With line breaks -->
<source>Click OK to save settings
and restart the application</source>
<translation>Haz clic en Aceptar para guardar la configuración
y reiniciar la aplicación</translation>
```

### Step 5: Testing Your Translation

#### 5.1 Validate Translation File
{: .no_toc}

Use the translation helper tool for file validation:

   ```bash
   # Check translation completeness for a specific language
   python translation_helper.py check YOUR_LANGUAGE
   # Example: python translation_helper.py check zh_CN

   # Validate translation file format and content
   python translation_helper.py validate YOUR_LANGUAGE
   # This checks for placeholder mismatches, HTML tag issues, etc.

   # View completion status for all languages
   python translation_helper.py stats
   ```

#### 5.2 Compile and Test Translation
{: .no_toc}

1. **Compile translation file**:   
   ```bash
   # Using translation helper tool (recommended)
   python translation_helper.py compile YOUR_LANGUAGE
   # Example: python translation_helper.py compile zh_CN
   
   # Or use PySide6 tools directly
   pyside6-lrelease locales/YOUR_LANGUAGE.ts
   ```

   **Note**: Compilation generates corresponding `.qm` files in the `locales/` directory. In this project, these `.qm` files are also committed to version control to ensure users can directly use translation features after downloading without additional compilation steps.

#### 5.3 Test in Application
{: .no_toc}

1. **Launch RimSort and switch language**:
   - Run `python -m app` to start the application
   - Click "Settings" in the menu bar
   - Find the "Language" option
   - Select your language from the dropdown menu
   - Restart the application when prompted to apply changes

2. **Functional testing**:
   - **Main interface**: Check menu bar, toolbar, and status bar text
   - **Settings dialog**: Verify all options and buttons are translated
   - **Mod management**: Test mod list, sorting, and filtering function labels
   - **Error messages**: Trigger some warnings or errors to check if messages are translated

3. **Visual inspection**:
   - **Text adaptation**: Ensure translated text displays completely in UI elements
   - **Button sizing**: Check if buttons can accommodate longer translated text
   - **Dialog layout**: Verify dialogs remain properly sized after displaying translations
   - **Tooltips**: Hover over various elements to check tooltip translations

### Step 6: Submit Your Contribution

1. **Commit your changes**:
   ```bash
   # Add translation files (including .ts source files and compiled .qm files)
   git add locales/YOUR_LANGUAGE.ts
   git add locales/YOUR_LANGUAGE.qm
   # If you added a new language, also update the language controller
   git add app/controllers/language_controller.py
   git commit -m "Add/Update [Language Name] translation"
   ```

   **Note**: Both `.ts` source files and compiled `.qm` files need to be committed in this project to ensure users can directly use translation features without additional compilation steps.

2. **Push to your fork**:
   ```bash
   git push origin translation-LANGUAGE_CODE
   ```

3. **Create Pull Request**:
   - Go to your fork on GitHub
   - Click "Compare & pull request" or "New Pull Request"
   - Select your translation branch as the source branch
   - Write a clear title in the format: "Add Portuguese translation" or "Update Chinese translation"
   - In the description, mention:
     - Translation completion percentage (e.g., "Completed 80% of string translations")
     - Main changes
     - Whether further testing is needed

**Pull Request Title Examples**:
- `Add French translation (fr_FR)`
- `Improve German translation - Fix interface terminology`
- `Update Japanese translation - Add settings page translations`

## Translation Status Tracking

You can check translation completeness by looking for:
- `type="unfinished"` entries (need translation)
- Empty `<translation></translation>` tags
- `type="obsolete"` entries (may need review)

## Maintenance and Updates

### When Source Code Changes

When RimSort's source code is updated, there may be new translatable strings added or existing strings modified. You will need to update translation files:

```bash
# Update translation files to include the latest translatable strings
python translation_helper.py update-ts YOUR_LANGUAGE
```

After updating, you only need to translate new or modified strings; existing translations will be preserved.

### Translation File Format
{: .no_toc}

The `.ts` files use XML format with this structure:
```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="LANGUAGE_CODE">
<context>
    <name>ClassName</name>
    <message>
        <location filename="../path/to/file.py" line="123"/>
        <source>English text</source>
        <translation>Translated text</translation>
    </message>
</context>
</TS>
```

Thank you for helping make RimSort accessible to users worldwide! 🌍