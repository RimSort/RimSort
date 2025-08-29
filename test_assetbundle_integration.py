#!/usr/bin/env python3
"""Test AssetBundle integration with DefParser."""

from pathlib import Path

from app.utils.def_parser import DefParser


def test_assetbundle_detection():
    """Test AssetBundle folder detection."""
    print("=== ASSETBUNDLE DETECTION TEST ===")
    
    # Test paths
    test_paths = [
        r"D:\Games\SteamLibrary\steamapps\common\RimWorld\Data\Ideology",
        r"D:\Games\SteamLibrary\steamapps\workshop\content\294100\2501661373", 
    ]
    
    for test_path in test_paths:
        if Path(test_path).exists():
            print(f"\nTesting: {test_path}")
            parser = DefParser(test_path)
            
            print(f"✓ Defs folder: {parser.defs_folder}")
            print(f"✓ Textures folder: {parser.textures_folder}")
            print(f"✓ AssetBundle folder: {parser.assetbundle_folder}")
            
            if parser.assetbundle_folder:
                # List AssetBundle files
                bundle_files = [f.name for f in parser.assetbundle_folder.iterdir() 
                               if f.is_file() and not f.name.endswith('.manifest')]
                print(f"✓ Bundle files: {bundle_files}")
        else:
            print(f"✗ Path not found: {test_path}")

def test_assetbundle_texture_extraction():
    """Test texture extraction from AssetBundles."""
    print("\n=== ASSETBUNDLE TEXTURE EXTRACTION TEST ===")
    
    # Test with Ideology DLC
    ideology_path = r"D:\Games\SteamLibrary\steamapps\common\RimWorld\Data\Ideology"
    if Path(ideology_path).exists():
        print(f"\nTesting Ideology DLC: {ideology_path}")
        parser = DefParser(ideology_path)
        
        if parser.assetbundle_folder:
            # Test some common texture paths that might be in AssetBundles
            test_textures = [
                "UI/Icons/IdeoSymbols/Cross",
                "Things/Pawn/Animal/Gauranlen",
                "UI/Gizmos/Tree",
                "UI/Icons/Tree",
                "Icon",  # Simple test
            ]
            
            for texture_path in test_textures:
                print(f"\nTrying to extract: {texture_path}")
                result = parser._extract_texture_from_assetbundle(texture_path)
                if result:
                    print(f"✓ Found: {result}")
                else:
                    print("✗ Not found")
    
    # Test with workshop mod  
    workshop_path = r"D:\Games\SteamLibrary\steamapps\workshop\content\294100\2501661373"
    if Path(workshop_path).exists():
        print(f"\nTesting workshop mod: {workshop_path}")
        parser = DefParser(workshop_path)
        
        if parser.assetbundle_folder:
            # Test texture extraction
            test_textures = [
                "Things/Item/Food/Canned",
                "UI/Icons/Canned", 
                "Food",
                "Can",
            ]
            
            for texture_path in test_textures:
                print(f"\nTrying to extract: {texture_path}")
                result = parser._extract_texture_from_assetbundle(texture_path)
                if result:
                    print(f"✓ Found: {result}")
                else:
                    print("✗ Not found")

def test_integrated_texture_resolution():
    """Test integrated texture resolution with AssetBundle fallback."""
    print("\n=== INTEGRATED TEXTURE RESOLUTION TEST ===")
    
    # Test with mods that have AssetBundles
    test_paths = [
        r"D:\Games\SteamLibrary\steamapps\workshop\content\294100\2501661373",
    ]
    
    for test_path in test_paths:
        if Path(test_path).exists():
            print(f"\nTesting: {test_path}")
            parser = DefParser(test_path)
            
            # Parse some defs
            defs = parser.parse_all_defs()
            print(f"Total definitions: {len(defs)}")
            
            # Test texture resolution for first few defs with texture paths
            tested = 0
            for def_info in defs:
                if tested >= 5:
                    break
                    
                display_path = def_info.get_display_texture_path()
                if display_path:
                    print(f"\nDef: {def_info.def_name} ({def_info.def_type})")
                    print(f"Display path: {display_path}")
                    
                    # Test texture resolution
                    texture_file = parser.get_texture_file_path(display_path)
                    if texture_file:
                        print(f"✓ Resolved to: {texture_file}")
                        if "temp" in texture_file.lower():
                            print("  (From AssetBundle)")
                        else:
                            print("  (From loose files)")
                    else:
                        print("✗ Could not resolve texture")
                    
                    tested += 1

if __name__ == "__main__":
    test_assetbundle_detection()
    test_assetbundle_texture_extraction()
    test_integrated_texture_resolution()

