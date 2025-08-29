#!/usr/bin/env python3
"""Explore actual texture names in AssetBundles to improve matching."""

from pathlib import Path

import UnityPy


def explore_texture_names():
    """Explore what texture names actually exist in AssetBundles."""
    
    bundles = [
        r"D:\Games\SteamLibrary\steamapps\workshop\content\294100\2501661373\Assets\AssetBundles\Mlie_CannedFood",
        r"D:\Games\SteamLibrary\steamapps\common\RimWorld\Data\Ideology\AssetBundles\resources_ideology",
    ]
    
    for bundle_path in bundles:
        if Path(bundle_path).exists():
            print(f"\n=== EXPLORING: {bundle_path} ===")
            
            try:
                env = UnityPy.load(bundle_path)
                
                texture_names = []
                for obj in env.objects:
                    if obj.type.name == 'Texture2D':
                        data = obj.read()
                        name = getattr(data, 'name', f'Texture_{obj.path_id}')
                        if name and name != f'Texture_{obj.path_id}':
                            texture_names.append(name)
                
                print(f"Total Texture2D objects: {len(list(env.objects))}")
                print(f"Textures with meaningful names: {len(texture_names)}")
                
                if texture_names:
                    print("✓ Named textures found:")
                    for name in sorted(texture_names)[:20]:  # Show first 20
                        print(f"  - {name}")
                    if len(texture_names) > 20:
                        print(f"  ... and {len(texture_names) - 20} more")
                else:
                    print("✗ No named textures found - all have hash IDs")
                    
                    # Show some hash examples
                    hash_examples = []
                    for obj in list(env.objects)[:10]:
                        if obj.type.name == 'Texture2D':
                            hash_examples.append(str(obj.path_id))
                    print("Example hash IDs:", hash_examples[:5])
                
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    explore_texture_names()

