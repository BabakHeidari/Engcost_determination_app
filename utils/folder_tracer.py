import os
import json
from pathlib import Path

def get_directory_structure(root_path):
    """
    Traverses directory structure and returns hierarchical data.
    
    Args:
        root_path: Root directory path to analyze
    
    Returns:
        Dictionary containing directory structure and separate lists by level
    """
    root_path = Path(root_path)
    
    # Store results
    structure = {}
    level1_folders = []
    level2_folders = []
    level3_folders = []
    
    # Track parent relationships
    folder_parents = {}
    
    # Walk through directory
    for item in root_path.iterdir():
        if item.is_dir():
            level1_folders.append(item.name)
            structure[item.name] = {}
            folder_parents[item.name] = root_path.name
            
            # Level 2
            for subitem in item.iterdir():
                if subitem.is_dir():
                    level2_folders.append(subitem.name)
                    structure[item.name][subitem.name] = []
                    folder_parents[subitem.name] = item.name
                    
                    # Level 3
                    for subsubitem in subitem.iterdir():
                        if subsubitem.is_dir():
                            level3_folders.append(subsubitem.name)
                            structure[item.name][subitem.name].append(subsubitem.name)
                            folder_parents[subsubitem.name] = subitem.name
    
    return {
        "structure": structure,
        "level1": level1_folders,
        "level2": level2_folders,
        "level3": level3_folders,
        "parents": folder_parents
    }

def create_metadata_json(root_path, output_file="__metadata.json"):
    """
    Creates metadata JSON file with directory structure.
    
    Args:
        root_path: Root directory to analyze
        output_file: Name of output JSON file
    """
    root_path = Path(root_path)
    
    # Get directory structure
    data = get_directory_structure(root_path)
    
    # Prepare JSON structure
    metadata = {
        "root_directory": str(root_path.absolute()),
        "directory_hierarchy": data["structure"],
        "folders_by_level": {
            "level_1": sorted(data["level1"]),
            "level_2": sorted(data["level2"]),
            "level_3": sorted(data["level3"])
        },
        "parent_relationships": data["parents"]
    }
    
    # Write to JSON file
    output_path = root_path / output_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"Metadata saved to: {output_path}")
    return metadata

def display_summary(metadata):
    """Display a readable summary of the directory structure."""
    print("\n" + "="*50)
    print("DIRECTORY STRUCTURE SUMMARY")
    print("="*50)
    
    print("\n📁 First Level Folders:")
    for folder in metadata["folders_by_level"]["level_1"]:
        print(f"  - {folder}")
    
    print("\n📁 Second Level Folders:")
    for folder in metadata["folders_by_level"]["level_2"]:
        parent = metadata["parent_relationships"].get(folder, "Unknown")
        print(f"  - {folder} (parent: {parent})")
    
    print("\n📁 Third Level Folders:")
    for folder in metadata["folders_by_level"]["level_3"]:
        parent = metadata["parent_relationships"].get(folder, "Unknown")
        print(f"  - {folder} (parent: {parent})")
    
    print("\n📊 Hierarchy View:")
    for parent, children in metadata["directory_hierarchy"].items():
        print(f"\n{parent}/")
        if isinstance(children, dict):
            for child, grandchildren in children.items():
                print(f"  ├── {child}/")
                if grandchildren:
                    for grandchild in grandchildren:
                        print(f"  │   └── {grandchild}/")
        else:
            print(f"  └── {children}")

# Alternative: Recursive approach for unlimited depth
def get_recursive_structure(path, current_depth=0, max_depth=None):
    """
    Recursively get directory structure with any depth.
    
    Args:
        path: Path to analyze
        current_depth: Current depth in recursion
        max_depth: Maximum depth to traverse (None for unlimited)
    """
    path = Path(path)
    structure = {}
    
    if max_depth is not None and current_depth >= max_depth:
        return None
    
    for item in path.iterdir():
        if item.is_dir():
            sub_structure = get_recursive_structure(item, current_depth + 1, max_depth)
            structure[item.name] = sub_structure if sub_structure else []
    
    return structure

def create_detailed_metadata(root_path, output_file="__metadata.json"):
    """
    Creates more detailed metadata including depth information.
    """
    root_path = Path(root_path)
    
    # Get recursive structure
    hierarchy = get_recursive_structure(root_path)
    
    # Collect folders by level
    folders_by_depth = {}
    parent_map = {}
    
    def collect_folders(path, current_path, depth):
        """Recursively collect folders with their depth and parent info."""
        if depth not in folders_by_depth:
            folders_by_depth[depth] = []
        
        for folder in path:
            if isinstance(path[folder], dict):
                folders_by_depth[depth].append(folder)
                parent_map[folder] = current_path.name if current_path else root_path.name
                collect_folders(path[folder], Path(str(current_path) + "/" + folder if current_path else folder), depth + 1)
            elif isinstance(path[folder], list):
                folders_by_depth[depth].append(folder)
                parent_map[folder] = current_path.name if current_path else root_path.name
    
    collect_folders(hierarchy, Path(), 1)
    
    # Prepare metadata
    metadata = {
        "root_directory": str(root_path.absolute()),
        "directory_hierarchy": hierarchy,
        "folders_by_depth": folders_by_depth,
        "parent_relationships": parent_map,
        "total_folders": len(parent_map)
    }
    
    # Save to JSON
    output_path = root_path / output_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return metadata

# Main execution
if __name__ == "__main__":
    # print(f"{os.getcwd()}\\Data\\Factories")
    # Specify your root directory
    root_directory = f"{os.getcwd()}\\Data\\Factories"  # Current directory, change to your path
    
    # Method 1: Basic metadata (3 levels only)
    print("Creating basic metadata...")
    metadata = create_metadata_json(root_directory, "__metadata.json")
    display_summary(metadata)
    
    # Method 2: Detailed metadata (unlimited depth)
    print("\n" + "="*50)
    print("Creating detailed metadata with unlimited depth...")
    detailed_metadata = create_detailed_metadata(root_directory, "__detailed_metadata.json")
    
    print(f"\n✅ Complete! Generated:")
    print(f"   - __metadata.json (basic structure)")
    print(f"   - __detailed_metadata.json (full recursive structure)")
    print(f"\nTotal folders found: {detailed_metadata['total_folders']}")