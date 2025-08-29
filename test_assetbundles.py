#!/usr/bin/env python3
"""Test script for exploring AssetBundle texture extraction."""

from pathlib import Path

import UnityPy


def explore_assetbundle(bundle_path: str):
    """Explore an AssetBundle and list its contents."""
    print(f"\n=== EXPLORING ASSETBUNDLE: {bundle_path} ===")
    
    try:
        # Load the AssetBundle
        env = UnityPy.load(bundle_path)
        
        print("Bundle loaded successfully")
        print(f"Objects in bundle: {len(list(env.objects))}")
        
        # List all objects
        textures_found = 0
        sprites_found = 0
        
        for obj in env.objects:
            try:
                if obj.type.name == 'Texture2D':
                    textures_found += 1
                    data = obj.read()
                    name = getattr(data, 'name', f'Texture_{obj.path_id}')
                    print(f"✓ Texture2D: {name}")
                    
                    # Try to get the texture image
                    try:
                        img = data.image
                        if img:
                            print(f"  - Size: {img.width}x{img.height}")
                            print(f"  - Format: {getattr(data, 'm_TextureFormat', 'Unknown')}")
                    except Exception as e:
                        print(f"  - Error reading image: {e}")
                        
                elif obj.type.name == 'Sprite':
                    sprites_found += 1
                    data = obj.read()
                    name = getattr(data, 'name', f'Sprite_{obj.path_id}')
                    print(f"• Sprite: {name}")
                    
                    # Check if sprite references a texture
                    try:
                        if hasattr(data, 'm_RD') and hasattr(data.m_RD, 'texture'):
                            tex_ref = data.m_RD.texture
                            print(f"  - References texture: {tex_ref}")
                    except Exception as e:
                        print(f"  - Error getting texture reference: {e}")
                        
            except Exception as e:
                print(f"Error processing object {obj.path_id}: {e}")
        
        print(f"\nTotal Texture2D objects: {textures_found}")
        print(f"Total Sprite objects: {sprites_found}")
        
    except Exception as e:
        print(f"Error loading bundle: {e}")

def main():
    """Test AssetBundle exploration."""
    
    # Test paths
    test_bundles = [
        r"D:\Games\SteamLibrary\steamapps\common\RimWorld\Data\Ideology\AssetBundles\resources_ideology",
        r"D:\Games\SteamLibrary\steamapps\workshop\content\294100\2501661373\Assets\AssetBundles\Mlie_CannedFood"
    ]
    
    for bundle_path in test_bundles:
        if Path(bundle_path).exists():
            explore_assetbundle(bundle_path)
        else:
            print(f"Bundle not found: {bundle_path}")

if __name__ == "__main__":
    main()
