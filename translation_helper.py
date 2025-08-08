"""
Enhanced Translation Helper Script for RimSort

This script helps translators by:
1. Checking translation completeness against source language
2. Validating translation files
3. Generating translation statistics
4. Running PySide6 translation tools
5. Auto-translating unfinished strings using various services

Usage:
    python translation_helper.py check zh_CN
    python translation_helper.py stats
    python translation_helper.py validate fr_FR
    python translation_helper.py update-ts zh_CN
    python translation_helper.py compile zh_CN
    python translation_helper.py compile-all
    python translation_helper.py auto-translate zh_CN --service google
    python translation_helper.py auto-translate zh_CN --service deepl --api-key YOUR_KEY
"""

import argparse
import importlib
import re
import shutil
import subprocess
import sys
import time
import types
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast

import requests

# Translation service imports with fallbacks
try:
    from googletrans import Translator as GoogleTranslator  # type: ignore
except ImportError:
    GoogleTranslator = None

openai: Optional[types.ModuleType]

try:
    openai = importlib.import_module("openai")
except ImportError:
    openai = None


# === Translation Services ===


class TranslationService:
    """translation service interface"""

    def translate(
        self, text: str, target_lang: str, source_lang: str = "en"
    ) -> Optional[str]:
        raise NotImplementedError


class GoogleTranslateService(TranslationService):
    """Google Translate service"""

    def __init__(self) -> None:
        if GoogleTranslator is None:
            raise ImportError("googletrans library not available")
        self.translator = GoogleTranslator()

    def translate(
        self, text: str, target_lang: str, source_lang: str = "en"
    ) -> Optional[str]:
        try:
            # Google language code mapping
            lang_map = {
                "zh_CN": "zh-cn",
                "en_US": "en",
                "ja_JP": "ja",
                "fr_FR": "fr",
                "de_DE": "de",
                "es_ES": "es",
                "ru_RU": "ru",
            }

            target = lang_map.get(target_lang, target_lang.lower().replace("_", "-"))
            source = lang_map.get(source_lang, source_lang.lower().replace("_", "-"))

            result = self.translator.translate(text, dest=target, src=source)
            return result.text
        except Exception as e:
            print(f"❌ Google translate failed: {e}")
            return None


class DeepLService(TranslationService):
    """DeepL translation service"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api-free.deepl.com/v2/translate"

    def translate(
        self, text: str, target_lang: str, source_lang: str = "en"
    ) -> Optional[str]:
        try:
            # DeepL language code mapping
            lang_map = {
                "zh_CN": "ZH",
                "zh_TW": "ZH",
                "en_US": "EN",
                "ja_JP": "JA",
                "ko_KR": "KO",
                "fr_FR": "FR",
                "de_DE": "DE",
                "es_ES": "ES",
            }

            target = lang_map.get(target_lang, target_lang.upper())
            source = lang_map.get(source_lang, source_lang.upper())

            data = {
                "auth_key": self.api_key,
                "text": text,
                "target_lang": target,
                "source_lang": source,
            }

            # Added timeout to the requests.post call
            response = requests.post(
                self.base_url, data=data, timeout=10
            )  # 10-second timeout
            response.raise_for_status()

            result = response.json()
            return result["translations"][0]["text"]

        except requests.exceptions.Timeout:
            print(f"❌ DeepL translation timed out: Request {text[:50]}...")
            return None
        except Exception as e:
            print(f"❌ DeepL translation failed: {e}")
            return None


class OpenAIService(TranslationService):
    """OpenAI GPT translation service"""

    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        if openai is None:
            raise ImportError("openai library not available")
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def translate(
        self, text: str, target_lang: str, source_lang: str = "en"
    ) -> Optional[str]:
        assert openai is not None
        try:
            # language name mapping
            lang_names = {
                "zh_CN": "Simplified Chinese",
                "zh_TW": "Traditional Chinese",
                "en_US": "English",
                "ja_JP": "Japanese",
                "ko_KR": "Korean",
                "fr_FR": "French",
                "de_DE": "German",
                "es_ES": "Spanish",
            }

            target_name = lang_names.get(target_lang, target_lang)
            source_name = lang_names.get(source_lang, source_lang)

            prompt = f"""Translate the following {source_name} text to {target_name}. 
This is UI text from a software application. Keep it concise and user-friendly.
Only return the translation, no explanation:

{text}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,
                # OpenAI client has its own timeout mechanism
                timeout=10.0,  # Added timeout
            )

            return response.choices[0].message.content.strip()

        except openai.TimeoutError:
            print(f"❌ OpenAI translation timed out: Request {text[:50]}...")
            return None
        except Exception as e:
            print(f"❌ OpenAI translation failed: {e}")
            return None


# === Existing Helper Functions ===


def get_source_keys(source_file: Path) -> Set[str]:
    """Extract all translation keys from source language file."""
    try:
        tree = ET.parse(source_file)
        root = tree.getroot()

        keys = set()
        for context in root.findall("context"):
            name_element = context.find("name")
            context_name = name_element.text if name_element is not None else "Unknown"

            for message in context.findall("message"):
                source = message.find("source")
                if source is not None and source.text:
                    # Create unique key from context + source
                    key = f"{context_name}::{source.text}"
                    keys.add(key)

        return keys
    except Exception:
        return set()


def parse_ts_file(
    file_path: Path, source_keys: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """Parse a .ts file and extract translation information."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        stats = {
            "total": 0,
            "translated": 0,
            "unfinished": 0,
            "obsolete": 0,
            "missing": 0,
        }

        issues = []
        translated_keys = set()

        for context in root.findall("context"):
            name_element = context.find("name")
            context_name = name_element.text if name_element is not None else "Unknown"

            for message in context.findall("message"):
                stats["total"] += 1

                source = message.find("source")
                translation = message.find("translation")

                source_text = source.text if source is not None and source.text else ""
                translated_keys.add(f"{context_name}::{source_text}")

                if translation is not None:
                    translation_type = translation.get("type")
                    translation_text = translation.text or ""

                    if translation_type == "unfinished":
                        stats["unfinished"] += 1
                        stats["missing"] += 1
                        issues.append(
                            f"Unfinished: {context_name} - {source_text[:50]}..."
                        )
                    elif translation_type == "obsolete":
                        stats["obsolete"] += 1
                    elif not translation_text.strip():
                        stats["missing"] += 1
                        issues.append(
                            f"Empty translation: {context_name} - {source_text[:50]}..."
                        )
                    else:
                        stats["translated"] += 1
                else:
                    stats["missing"] += 1
                    issues.append(
                        f"Missing translation tag: {context_name} - {source_text[:50]}..."
                    )

        # Calculate missing keys based on source language
        if source_keys:
            missing_keys = source_keys - translated_keys
            stats["missing_from_source"] = len(missing_keys)

            for key in list(missing_keys)[:5]:  # Show first 5 missing keys
                context_key, source_text_key = key.split("::", 1)
                issues.append(
                    f"Missing from source: {context_key} - {source_text_key[:50]}..."
                )

        return {
            "stats": stats,
            "issues": issues,
            "language": root.get("language", "unknown"),
        }

    except Exception as e:
        return {"error": str(e)}


# === New Auto-Translation Functions ===


@dataclass
class UnfinishedItem:
    context: str
    source: str
    element: ET.Element


def find_unfinished_translations(
    tree: ET.ElementTree,
) -> List[UnfinishedItem]:
    """Search for unfinished translations in a .ts file."""
    unfinished: list[UnfinishedItem] = []
    root = tree.getroot()

    if root is None:
        return []

    for context in root.findall("context"):
        context_name = context.findtext("name") or "Unknown"

        for msg in context.findall("message"):
            src_elem = msg.find("source")
            tr_elem = msg.find("translation")
            if src_elem is None or tr_elem is None:
                continue

            src_text = (src_elem.text or "").strip()
            tr_text = (tr_elem.text or "").strip()
            tr_type = (tr_elem.get("type") or "").strip()

            if tr_type == "unfinished" or not tr_text:
                unfinished.append(
                    UnfinishedItem(
                        context=context_name.strip(),
                        source=src_text,
                        element=tr_elem,
                    )
                )

    return unfinished


def should_skip_translation(text: str) -> bool:
    """judge if a text should be skipped for translation"""
    if not text.strip():
        return True
    if len(text.strip()) <= 1:
        return True
    if text.isdigit():
        return True
    if re.match(r"^[^\w\s]+$", text):
        return True
    return False


def create_translation_service(service_name: str, **kwargs: Any) -> TranslationService:
    """create translation service instance"""
    if service_name == "google":
        if GoogleTranslator is None:
            raise ImportError(
                "googletrans not available. Install with: pip install googletrans==4.0.0rc1"
            )
        return GoogleTranslateService()

    elif service_name == "deepl":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("DeepL requires API key")
        return DeepLService(api_key)

    elif service_name == "openai":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("OpenAI requires API key")
        model = kwargs.get("model", "gpt-3.5-turbo")
        return OpenAIService(api_key, model)

    else:
        raise ValueError(f"Unsupported translation service: {service_name}")


def auto_translate_file(
    language: str, service_name: str = "google", **service_kwargs: Any
) -> bool:
    """auto-translate unfinished strings in a .ts file"""
    locales_dir = Path("locales")
    ts_file = locales_dir / f"{language}.ts"

    if not ts_file.exists():
        print(f"❌ Translation file not found: {ts_file}")
        return False

    # Create a backup copy
    backup_file = ts_file.with_suffix(".ts.backup")
    shutil.copy2(ts_file, backup_file)
    print(f"📁 Backup created: {backup_file}")

    translation_failed_midway = False
    tree: ET.ElementTree = ET.ElementTree()
    successful = 0
    failed = 0

    try:
        # Create translation service
        service = create_translation_service(service_name, **service_kwargs)

        # Parse file
        tree = cast(Any, ET).parse(ts_file)
        unfinished = find_unfinished_translations(tree)

        if not unfinished:
            print("✅ No unfinished translations found!")
            return True

        print(f"🔍 Found {len(unfinished)} unfinished translations")

        for i, item in enumerate(unfinished, 1):
            source_text = item.source

            if should_skip_translation(source_text):
                print(f"⏭️  Skipping [{i}/{len(unfinished)}]: {source_text}")
                continue

            print(f"🔄 Translating [{i}/{len(unfinished)}]: {source_text[:50]}...")

            # Attempt translation
            translated = service.translate(source_text, language, "en_US")

            if translated and translated.strip():
                # Update XML element
                item.element.text = translated
                if item.element.get("type") == "unfinished":
                    del item.element.attrib["type"]

                print(f"✅ Success: {translated[:50]}...")
                successful += 1
            else:
                print(f"❌ Failed to translate: {source_text[:50]}...")
                failed += 1
                break  # Exit the loop immediately on first failure

            # Add delay to avoid API limits
            time.sleep(0.5)

    except Exception as e:
        print(f"⚠️  An unexpected error occurred during auto-translation: {e}")
        translation_failed_midway = True  # Mark as failed if an exception occurs

    finally:
        # Only save if no translation failed midway, or if you want to explicitly save partial results
        # we will save only if NO failures occurred during the loop.
        if not translation_failed_midway:
            try:
                # Save file
                ET.register_namespace("", "")
                tree.write(ts_file, encoding="utf-8", xml_declaration=True)

                # Fix DOCTYPE
                with open(ts_file, "r", encoding="utf-8") as f:
                    content = f.read()

                if "<!DOCTYPE TS>" not in content:
                    lines = content.split("\n")
                    lines.insert(1, "<!DOCTYPE TS>")
                    content = "\n".join(lines)

                with open(ts_file, "w", encoding="utf-8") as f:
                    f.write(content)

                print("\n📊 Auto-translation completed:")
                print(f"   ✅ Successful: {successful}")
                print(f"   ❌ Failed: {failed}")  # This will be 0 if saving happened
                print(f"   📁 File updated: {ts_file}")
                # Remove backup if successful save
                if backup_file.exists():
                    backup_file.unlink()
                    print(f"🗑️  Backup removed: {backup_file}")
                return True
            except Exception as save_e:
                print(f"❌ Error saving the file: {save_e}")
                print(f"🔄 Restoring from backup: {backup_file}")
                if backup_file.exists():
                    shutil.copy2(backup_file, ts_file)
                return False
        else:
            print(
                "\n❌ Auto-translation aborted due to failure. Restoring from backup."
            )
            if backup_file.exists():
                shutil.copy2(backup_file, ts_file)
                # No need to unlink backup here, it's the working copy now
            return False


def run_lupdate(language: Optional[str] = None) -> bool:
    """Run pyside6-lupdate to update translation files."""
    try:
        # Check if pyside6-lupdate is available
        cmd = ["pyside6-lupdate"]

        # Find all Python source files in the app directory
        py_files = list(Path("app").rglob("*.py"))
        if not py_files:
            print("⚠️ No Python source files found under app/")
            return False

        cmd.extend(str(f) for f in py_files)

        # If a specific language is provided, update that .ts file
        if language:
            print(f"🔄 Updating translation file for {language}...")
            cmd.extend(
                ["-ts", f"locales/{language}.ts", "-no-obsolete", "-locations", "none"]
            )
        else:
            print("🔄 Updating all translation files...")
            locales_dir = Path("locales")
            ts_files = list(locales_dir.glob("*.ts"))
            if ts_files:
                cmd.extend(
                    ["-ts"]
                    + [str(f) for f in ts_files]
                    + ["-no-obsolete", "-locations", "none"]
                )
            else:
                print("⚠️ No .ts files found in locales/")
                return False

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Translation files updated successfully!")
            return True
        else:
            print(f"❌ Error running lupdate:\n{result.stderr}")
            return False

    except FileNotFoundError:
        print("❌ pyside6-lupdate not found. Please install PySide6-Essentials.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_lrelease(language: Optional[str] = None) -> bool:
    """Run pyside6-lrelease to compile translation files."""
    try:
        locales_dir = Path("locales")
        if not locales_dir.exists():
            print("❌ Locales directory not found")
            return False

        if language:
            ts_file = locales_dir / f"{language}.ts"
            if not ts_file.exists():
                print(f"❌ Translation file not found: {ts_file}")
                return False

            print(f"🔄 Compiling translation for {language}...")
            cmd = ["pyside6-lrelease", str(ts_file)]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ Translation compiled: {language}.qm")
                return True
            else:
                print(f"❌ Error compiling {language}: {result.stderr}")
                return False
        else:
            print("🔄 Compiling all translation files...")
            ts_files = list(locales_dir.glob("*.ts"))
            success_count = 0

            for ts_file in ts_files:
                cmd = ["pyside6-lrelease", str(ts_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    print(f"✅ Compiled: {ts_file.stem}.qm")
                    success_count += 1
                else:
                    print(f"❌ Failed to compile {ts_file.stem}: {result.stderr}")

            print(f"📊 Compiled {success_count}/{len(ts_files)} translation files")
            return success_count > 0

    except FileNotFoundError:
        print("❌ pyside6-lrelease not found. Please install PySide6-Essentials.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_translation(language: str) -> None:
    """Check translation completeness for a specific language."""
    locales_dir = Path("locales")
    ts_file = locales_dir / f"{language}.ts"
    source_file = locales_dir / "en_US.ts"  # Assume en_US is source

    if not ts_file.exists():
        print(f"❌ Translation file not found: {ts_file}")
        return

    print(f"🔍 Checking translation for {language}...")

    # Get source keys for comparison
    source_keys = set()
    if source_file.exists():
        source_keys = get_source_keys(source_file)
        print(f"📚 Found {len(source_keys)} keys in source language")

    result = parse_ts_file(ts_file, source_keys)

    if "error" in result:
        print(f"❌ Error parsing file: {result['error']}")
        return

    stats = result["stats"]
    issues = result["issues"]

    print("\n📊 Translation Statistics:")
    print(f"   Total strings: {stats['total']}")
    print(
        f"   Translated: {stats['translated']} ({stats['translated'] / stats['total'] * 100:.1f}%)"
    )
    print(f"   Unfinished: {stats['unfinished']}")
    print(f"   Missing: {stats['missing']}")
    print(f"   Obsolete: {stats['obsolete']}")

    if source_keys and "missing_from_source" in stats:
        print(f"   Missing from source: {stats['missing_from_source']}")

    completion = (
        (stats["translated"] / stats["total"]) * 100 if stats["total"] > 0 else 0
    )

    if completion >= 95:
        print("✅ Translation is nearly complete!")
    elif completion >= 80:
        print("🟡 Translation is mostly complete")
    elif completion >= 50:
        print("🟠 Translation is partially complete")
    else:
        print("🔴 Translation needs significant work")

    if issues and len(issues) <= 10:
        print("\n⚠️  Issues found:")
        for issue in issues[:10]:
            print(f"   • {issue}")
        if len(issues) > 10:
            print(f"   ... and {len(issues) - 10} more issues")


def show_all_stats() -> None:
    """Show statistics for all available translations."""
    locales_dir = Path("locales")
    if not locales_dir.exists():
        print("❌ Locales directory not found")
        return

    ts_files = list(locales_dir.glob("*.ts"))
    if not ts_files:
        print("❌ No translation files found")
        return

    # Get source keys
    source_file = locales_dir / "en_US.ts"
    source_keys = set()
    if source_file.exists():
        source_keys = get_source_keys(source_file)

    print("📊 Translation Statistics for All Languages:\n")
    print(
        f"{'Language':<10} {'Progress':<10} {'Translated':<12} {'Unfinished ':<12} {'Missing':<12} {'Status'}"
    )
    print("-" * 75)

    for ts_file in sorted(ts_files):
        language = ts_file.stem
        result = parse_ts_file(ts_file, source_keys if language != "en_US" else None)

        if "error" in result:
            print(
                f"{language:<10} {'ERROR':<10} {'N/A':<12} {'N/A':<10} {'N/A':<12} ❌"
            )
            continue

        stats = result["stats"]
        completion = (
            (stats["translated"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )

        status = (
            "✅"
            if completion >= 95
            else "🟡"
            if completion >= 80
            else "🟠"
            if completion >= 50
            else "🔴"
        )

        missing_from_source = stats.get("missing_from_source", 0)

        print(
            f"{language:<10} {completion:>6.1f}% {stats['translated']:>9}/{stats['total']:<4} {stats['unfinished']:>10} {missing_from_source:>10} {status:>8}"
        )


def validate_translation(language: str) -> None:
    """Validate a translation file for common issues."""
    locales_dir = Path("locales")
    ts_file = locales_dir / f"{language}.ts"

    if not ts_file.exists():
        print(f"❌ Translation file not found: {ts_file}")
        return

    print(f"🔍 Validating translation for {language}...")

    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()

        issues = []

        # Check XML structure
        if root.tag != "TS":
            issues.append("❌ Root element should be 'TS'")

        if not root.get("language"):
            issues.append("❌ Missing language attribute")

        # Check for common translation issues
        for context in root.findall("context"):
            for message in context.findall("message"):
                source = message.find("source")
                translation = message.find("translation")

                if source is not None and translation is not None:
                    source_text = source.text or ""
                    trans_text = translation.text or ""

                    # Check for placeholder mismatches
                    source_placeholders = set(re.findall(r"\{[^}]+\}", source_text))
                    trans_placeholders = set(re.findall(r"\{[^}]+\}", trans_text))

                    if source_placeholders != trans_placeholders and trans_text:
                        issues.append(
                            f"⚠️  Placeholder mismatch: '{source_text[:30]}...' -> '{trans_text[:30]}...'"
                        )

                    # Check for HTML tag mismatches
                    source_tags = set(re.findall(r"<[^>]+>", source_text))
                    trans_tags = set(re.findall(r"<[^>]+>", trans_text))

                    if source_tags != trans_tags and trans_text:
                        issues.append(
                            f"⚠️  HTML tag mismatch: '{source_text[:30]}...' -> '{trans_text[:30]}...'"
                        )

        if not issues:
            print("✅ Translation file is valid!")
        else:
            print(f"⚠️  Found {len(issues)} validation issues:")
            for issue in issues[:10]:
                print(f"   {issue}")
            if len(issues) > 10:
                print(f"   ... and {len(issues) - 10} more issues")

    except Exception as e:
        print(f"❌ Error validating file: {e}")


def process_language(language: str, service: str, **service_kwargs: Any) -> None:
    """Run the full pipeline for a single language."""
    print(f"🚀 Starting one-click process for {language} ...")

    if not run_lupdate(language):
        print("❌ Aborting: lupdate failed.")
        sys.exit(1)

    if not auto_translate_file(language, service, **service_kwargs):
        print("❌ Aborting: auto-translation failed.")
        sys.exit(1)

    if not run_lrelease(language):
        print("❌ Aborting: lrelease failed.")
        sys.exit(1)

    print("✅ One-click process completed successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhanced RimSort Translation Helper")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check translation completeness")
    check_parser.add_argument("language", help="Language code (e.g., zh_CN)")

    # Stats command
    subparsers.add_parser("stats", help="Show statistics for all translations")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate translation file"
    )
    validate_parser.add_argument("language", help="Language code (e.g., zh_CN)")

    # Update command
    update_parser = subparsers.add_parser(
        "update-ts", help="Update translation files using lupdate"
    )
    update_parser.add_argument(
        "language",
        nargs="?",
        help="Language code (optional, updates all if not specified)",
    )

    # Compile command
    compile_parser = subparsers.add_parser(
        "compile", help="Compile translation file using lrelease"
    )
    compile_parser.add_argument("language", help="Language code (e.g., zh_CN)")

    # Compile all command
    subparsers.add_parser("compile-all", help="Compile all translation files")

    # Auto-translate command
    auto_parser = subparsers.add_parser(
        "auto-translate", help="Auto-translate unfinished strings"
    )
    auto_parser.add_argument("language", help="Language code (e.g., zh_CN)")
    auto_parser.add_argument(
        "--service",
        choices=["google", "deepl", "openai"],
        default="google",
        help="Translation service",
    )
    auto_parser.add_argument("--api-key", help="API key for DeepL/OpenAI")
    auto_parser.add_argument(
        "--model", default="gpt-3.5-turbo", help="OpenAI model to use"
    )

    process_parser = subparsers.add_parser(
        "process",
        help="One-click workflow: update .ts → auto-translate missing strings → compile .qm",
    )
    process_parser.add_argument("language", help="Language code, e.g. zh_CN")
    process_parser.add_argument(
        "--service",
        choices=["google", "deepl", "openai"],
        default="google",
        help="Translation service to use for auto-translation",
    )
    process_parser.add_argument("--api-key", help="API key for DeepL/OpenAI")
    process_parser.add_argument(
        "--model", default="gpt-3.5-turbo", help="OpenAI model name"
    )

    args = parser.parse_args()

    if args.command == "check":
        check_translation(args.language)
    elif args.command == "stats":
        show_all_stats()
    elif args.command == "validate":
        validate_translation(args.language)
    elif args.command == "update-ts":
        run_lupdate(args.language)
    elif args.command == "compile":
        run_lrelease(args.language)
    elif args.command == "compile-all":
        run_lrelease()
    elif args.command == "auto-translate":
        service_kwargs = {}
        if args.api_key:
            service_kwargs["api_key"] = args.api_key
        if args.model:
            service_kwargs["model"] = args.model

        success = auto_translate_file(args.language, args.service, **service_kwargs)
        if not success:
            sys.exit(1)
    elif args.command == "process":
        service_kwargs = {}
        if args.api_key:
            service_kwargs["api_key"] = args.api_key
        if args.model:
            service_kwargs["model"] = args.model
        process_language(args.language, args.service, **service_kwargs)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
