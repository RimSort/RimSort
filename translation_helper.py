"""
Translation Helper Script for RimSort

This script helps translators by:
1. Checking translation completeness against source language
2. Validating translation files
3. Generating translation statistics
4. Running PySide6 translation tools

Usage:
    python translation_helper.py check zh_CN
    python translation_helper.py stats
    python translation_helper.py validate fr_FR
    python translation_helper.py update-ts zh_CN
    python translation_helper.py compile zh_CN
    python translation_helper.py compile-all
"""

import argparse
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional, Set


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
                    )  # Calculate missing keys based on source language
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
            cmd.extend(["-ts", f"locales/{language}.ts", "-no-obsolete", "-locations", "none"])
        else:
            print("🔄 Updating all translation files...")
            locales_dir = Path("locales")
            ts_files = list(locales_dir.glob("*.ts"))
            if ts_files:
                cmd.extend(["-ts"] + [str(f) for f in ts_files])
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
                    import re

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


def main() -> None:
    parser = argparse.ArgumentParser(description="RimSort Translation Helper")
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
