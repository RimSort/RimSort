import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, List, Tuple


def find_xml_files(mods_path: str) -> List[str]:
    """find all xml files in mods directory"""
    xml_files = []
    for root, _, files in os.walk(mods_path):
        for file in files:
            if file.lower().endswith(".xml"):
                xml_files.append(os.path.join(root, file))
    return xml_files


def extract_text_from_xml(file_path: str) -> List[str]:
    """extract text content and attribute values from xml file"""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # get all text content and attribute values
        texts = []
        for elem in root.iter():
            # get text content
            if elem.text and elem.text.strip():
                texts.extend(re.findall(r"\w+", elem.text))

            # get attribute values
            for attr in elem.attrib.values():
                if attr and attr.strip():
                    texts.extend(re.findall(r"\w+", attr))

        return texts
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return []


def analyze_terms(
    mods_path: str, sample_size: int = 100
) -> Tuple[Dict[str, int], List[str], List[str]]:
    """analyze xml files to find common and rare terms"""
    # get list of xml files
    xml_files = find_xml_files(mods_path)
    print(f"Found {len(xml_files)} XML files")

    # sample files if there are too many
    if sample_size and len(xml_files) > sample_size:
        import random

        xml_files = random.sample(xml_files, sample_size)
        print(f"Sampling {sample_size} files for analysis")

    # collect all terms
    term_counter = Counter()
    for file in xml_files:
        terms = extract_text_from_xml(file)
        # only count terms with 4 or more characters
        terms = [term for term in terms if len(term) >= 4]
        term_counter.update(terms)

    # find common and rare terms
    common_terms = [term for term, count in term_counter.most_common(10)]
    rare_terms = [
        term for term, count in term_counter.most_common()[:-11:-1] if count > 1
    ]

    return dict(term_counter), common_terms, rare_terms


def main():
    mods_path = r"D:\Games\Rimworld\Mods"

    print("Analyzing XML files for search terms...")
    term_counts, common_terms, rare_terms = analyze_terms(mods_path)

    print("\nMost Common Terms:")
    print("-" * 40)
    for term in common_terms:
        print(f"{term:<20} {term_counts[term]:>10} occurrences")

    print("\nRare Terms:")
    print("-" * 40)
    for term in rare_terms:
        print(f"{term:<20} {term_counts[term]:>10} occurrences")

    # suggest search scenarios
    print("\nSuggested Search Scenarios:")
    print("-" * 40)
    print("Common terms for benchmarking:")
    for term in common_terms[:3]:
        print(f'    "{term}",  # {term_counts[term]} occurrences')

    print("\nRare terms for benchmarking:")
    for term in rare_terms[:3]:
        print(f'    "{term}",  # {term_counts[term]} occurrences')


if __name__ == "__main__":
    main()
