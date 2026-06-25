import os
import json
import math
import argparse
from typing import List, Dict, Any, Optional, Set, Tuple
import nbtlib
from beartype import beartype

# Constants
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

@beartype
def decode_varints(byte_array: List[int]) -> List[int]:
    """
    Decodes a byte array containing VarInts (used by Sponge schematics for BlockData)
    into a list of integers.
    """
    result = []
    i = 0
    length = len(byte_array)
    while i < length:
        value = 0
        position = 0
        while True:
            if i >= length:
                break
            byte = byte_array[i]
            # Ensure it's treated as unsigned byte (some byte array items might be negative in python based on nbtlib but usually 0-255)
            byte = byte & 0xFF
            i += 1
            value |= (byte & 0x7F) << position
            if (byte & 0x80) == 0:
                break
            position += 7
        result.append(value)
    return result

@beartype
def extract_tag_dict(entity_compound: nbtlib.Compound) -> Dict[str, Any]:
    """
    Converts a BlockEntity NBT compound into a standard Python dict.
    Strips out positional properties so the tag can be reused for identical blocks
    at different locations.
    """
    tag_copy = dict(entity_compound)
    # Remove position and ID, as we only want the internal properties of the entity
    for key in ['Pos', 'x', 'y', 'z', 'Id', 'id']:
        tag_copy.pop(key, None)
        
    def to_python(val: Any) -> Any:
        if isinstance(val, nbtlib.Compound) or isinstance(val, dict):
            return {str(k): to_python(v) for k, v in val.items()}
        elif isinstance(val, nbtlib.List) or isinstance(val, list):
            return [to_python(v) for v in val]
        elif isinstance(val, nbtlib.String):
            return str(val)
        elif isinstance(val, nbtlib.Numeric):
            return val.real
        elif isinstance(val, (nbtlib.IntArray, nbtlib.ByteArray, nbtlib.LongArray)):
            return [int(x) for x in val]
        return val
        
    return to_python(tag_copy)

class PaletteManager:
    """
    Manages the character palette, assigning a unique UTF-8 character to each unique
    block (and optional tag).
    """
    def __init__(self):
        self.palette_map: Dict[str, Dict[str, Any]] = {" ": {"block": "minecraft:air"}}
        self.reverse_map: Dict[str, str] = {"minecraft:air_None": " "}
        self.char_generator = self._char_gen()
        
    def _char_gen(self):
        """
        Generator for printable UTF-8 characters.
        Skips space (0x0020) since it's reserved for air.
        """
        code_point = 0x00A1  # Start at inverted exclamation mark
        while True:
            if code_point == 0x0020:
                code_point += 1
                continue
            try:
                char = chr(code_point)
                if char.isprintable() and not char.isspace():
                    yield char
            except ValueError:
                pass
            code_point += 1
            if code_point > 0x10FFFF:
                raise RuntimeError("Ran out of unique UTF-8 characters!")

    @beartype
    def get_char(self, block_id: str, tag_dict: Optional[Dict[str, Any]] = None) -> str:
        """
        Gets or creates a character for a specific block and its tag.
        """
        if block_id == "minecraft:air" and not tag_dict:
            return " "
            
        # Serialize the tag dictionary deterministically for the lookup key
        tag_str = json.dumps(tag_dict, sort_keys=True) if tag_dict else "None"
        key = f"{block_id}_{tag_str}"
        
        if key in self.reverse_map:
            return self.reverse_map[key]
            
        new_char = next(self.char_generator)
        self.reverse_map[key] = new_char
        self.palette_map[new_char] = {"block": block_id}
        if tag_dict:
            self.palette_map[new_char]["tag"] = tag_dict
            
        return new_char
        
    @beartype
    def to_dict(self) -> Dict[str, Any]:
        """Returns the palette mapped out for JSON serialization."""
        res = []
        for char, data in self.palette_map.items():
            entry = {"char": char, "block": data["block"]}
            if "tag" in data:
                entry["tag"] = data["tag"]
            res.append(entry)
        return {"palette": res}

class SchematicParser:
    """
    Parses a schematic file into a 3D grid and assigns characters using PaletteManager.
    """
    def __init__(self, file_path: str, taglist: Set[str], palette_mgr: PaletteManager):
        self.file_path = file_path
        self.taglist = taglist
        self.palette_mgr = palette_mgr
        
        try:
            self.nbt_data = nbtlib.load(self.file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load schematic file '{self.file_path}': {e}")
            
        root = self.nbt_data
        
        # Read dimensions
        self.width = int(root.get("Width", 0))
        self.height = int(root.get("Height", 0))
        self.length = int(root.get("Length", 0))
        
        if self.width == 0 or self.height == 0 or self.length == 0:
            raise ValueError(f"Invalid dimensions in schematic: {self.width}x{self.height}x{self.length}")
            
        # Parse Palette
        raw_palette = root.get("Palette", {})
        self.id_to_block = {int(v): str(k) for k, v in raw_palette.items()}
        
        # Determine format of BlockData
        raw_block_data = root.get("BlockData", [])
        self.block_data = decode_varints(list(raw_block_data))
        
        # Map BlockEntities (x,y,z -> tag)
        self.entity_map = {}
        block_entities = root.get("BlockEntities", [])
        for entity in block_entities:
            pos = entity.get("Pos")
            if pos and len(pos) >= 3:
                x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
                self.entity_map[(x, y, z)] = extract_tag_dict(entity)
                
    @beartype
    def get_char_for_block(self, x: int, y: int, z: int) -> str:
        """Returns the palette character for a specific coordinate."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height or z < 0 or z >= self.length:
            return " "
            
        # Standard Sponge BlockData index logic: (y * length + z) * width + x
        index = (y * self.length + z) * self.width + x
        if index >= len(self.block_data):
            return " "
            
        block_val = self.block_data[index]
        block_name = self.id_to_block.get(block_val, "minecraft:air")
        
        tag_dict = None
        # Extract base block name without properties (e.g., 'minecraft:chest[facing=north]' -> 'minecraft:chest')
        base_block_name = block_name.split('[')[0]
        if block_name in self.taglist or base_block_name in self.taglist:
            entity = self.entity_map.get((x, y, z))
            
            # Fastpaintings multi-block check
            if not entity and base_block_name == "fastpaintings:painting" and '[' in block_name:
                props_str = block_name.split('[')[1].split(']')[0]
                props = dict(p.split('=') for p in props_str.split(','))
                x_off = int(props.get('x_offset', 0))
                y_off = int(props.get('y_offset', 0))
                
                if x_off != 0 or y_off != 0:
                    ox_candidates = [x + x_off, x - x_off, x]
                    oz_candidates = [z + x_off, z - x_off, z]
                    oy = y + y_off
                    
                    for ox in ox_candidates:
                        for oz in oz_candidates:
                            if abs(ox - x) + abs(oz - z) == x_off:
                                ent = self.entity_map.get((ox, oy, oz))
                                if ent and "variant" in ent:
                                    entity = ent
                                    break
                        if entity:
                            break
                            
            if entity:
                if base_block_name == "fastpaintings:painting":
                    variant = entity.get("variant")
                    if variant is not None:
                        tag_dict = {"variant": str(variant)}
                else:
                    tag_dict = dict(entity)
            
        return self.palette_mgr.get_char(block_name, tag_dict)
        
    @beartype
    def generate_slice(self, start_x: int, start_z: int, start_y: int, height: int) -> List[List[str]]:
        """
        Extracts a chunk of blocks (16x16 in X/Z) for a specific height range.
        Returns a list of layers, where each layer is a list of strings representing the Z rows.
        """
        slices = []
        end_y = start_y + height
        for y in range(start_y, end_y):
            layer = []
            for dz in range(16):
                z = start_z + dz
                row_chars = []
                for dx in range(16):
                    x = start_x + dx
                    char = self.get_char_for_block(x, y, z)
                    row_chars.append(char)
                layer.append("".join(row_chars))
            slices.append(layer)
        return slices

@beartype
def generate_building(
    parser: SchematicParser,
    base_name: str,
    palette_name: str,
    cellar_count: int,
    floor_count: int,
    unique: bool,
    start_x: int = 0,
    start_z: int = 0,
    embedded_palette: bool = False
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Generates the parts and the building layout definition.
    Returns a tuple containing the building JSON and a list of part JSON file objects.
    """
    building_parts = []
    generated_files = []
    
    total_segments = cellar_count + 1 + floor_count # Cellars + Ground + Floors
    
    for segment_index in range(total_segments):
        start_y = segment_index * 6
        height = 6
        
        if segment_index < cellar_count:
            # cellars: bottom to top
            cellar_idx = cellar_count - 1 - segment_index
            name_suffix = f"cellar{cellar_idx}"
            type_flags = {"cellar": True, "ground": False, "top": False}
        elif segment_index == cellar_count:
            # ground
            name_suffix = "ground"
            type_flags = {"cellar": False, "ground": True, "top": False, "floor": 0}
        else:
            # floors
            floor_idx = segment_index - cellar_count
            name_suffix = f"floor{floor_idx}"
            type_flags = {"cellar": False, "ground": False, "top": False, "floor": floor_idx}
            
        part_name = f"{base_name}_{name_suffix}"
        
        # Copy flags for the building JSON
        b_ref = dict(type_flags)
        b_ref["part"] = part_name
        
        if not unique:
            # Remove "floor" requirement so the game can randomly select among generic floors
            b_ref.pop("floor", None)
            
        building_parts.append(b_ref)
        
        # Extract block slices for this part
        slices = parser.generate_slice(start_x, start_z, start_y, height)
        part_json = {"xsize": 16, "zsize": 16, "slices": slices}
        
        if embedded_palette:
            part_json["palette"] = parser.palette_mgr.to_dict()
        else:
            part_json["refpalette"] = palette_name
            
        generated_files.append({"name": f"{part_name}.json", "content": part_json})
        
    # Process the top segment (anything remaining above the structured 6-block segments)
    top_start_y = total_segments * 6
    if top_start_y < parser.height:
        top_height = parser.height - top_start_y
        name_suffix = "top"
        part_name = f"{base_name}_{name_suffix}"
        
        b_ref = {"cellar": False, "ground": False, "top": True, "part": part_name}
        building_parts.append(b_ref)
        
        slices = parser.generate_slice(start_x, start_z, top_start_y, top_height)
        part_json = {"xsize": 16, "zsize": 16, "slices": slices}
        
        if embedded_palette:
            part_json["palette"] = parser.palette_mgr.to_dict()
        else:
            part_json["refpalette"] = palette_name
            
        generated_files.append({"name": f"{part_name}.json", "content": part_json})

    building_json = {
        "filler": "#",
        "rubble": "}",
        "allowDoors": False,
        "mincellars": cellar_count if cellar_count > 0 else 0,
        "maxcellars": cellar_count if cellar_count > 0 else 0,
        "minfloors": floor_count if floor_count > 0 else 0,
        "maxfloors": floor_count if floor_count > 0 else 0,
        "parts": building_parts
    }
    
    return building_json, generated_files

@beartype
def save_json(path: str, data: Any):
    """Helper to save dicts as pretty JSON files."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Saved: {path}")

def main():
    parser = argparse.ArgumentParser(description="Convert Minecraft .schem files into Lost Cities generation parts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_args(p):
        p.add_argument("filename", help="Path to the input .schem file")
        p.add_argument("-d", "--dir", default="", help="Output directory path")
        p.add_argument("--taglist", default="", help="Comma-separated block IDs to preserve NBT tags for (e.g. minecraft:chest)")
        p.add_argument("--name", default="", help="Base name (defaults to schematic filename without extension)")

    # Command: part
    part_p = subparsers.add_parser("part", help="Generate a single standalone part (fails if not exactly 16x16 footprint)")
    add_common_args(part_p)

    # Command: building
    bldg_p = subparsers.add_parser("building", help="Generate a building file and its structured vertical parts")
    add_common_args(bldg_p)
    bldg_p.add_argument("-c", "--cellars", type=int, default=0, help="Number of 6-block tall cellars")
    bldg_p.add_argument("-f", "--floors", type=int, default=0, help="Number of 6-block tall floors")
    bldg_p.add_argument("-u", "--unique", action="store_true", help="Make parts unique to exact floors rather than generic variants")

    # Command: multibuilding
    multi_p = subparsers.add_parser("multibuilding", help="Generate a grid of buildings from a large schematic")
    add_common_args(multi_p)
    multi_p.add_argument("-c", "--cellars", type=int, default=0, help="Number of cellars for each building column")
    multi_p.add_argument("-f", "--floors", type=int, default=0, help="Number of floors for each building column")
    multi_p.add_argument("-u", "--unique", action="store_true", help="Make parts unique to exact floors")
    
    args = parser.parse_args()
    
    taglist = set([t.strip() for t in args.taglist.split(",") if t.strip()])
    
    base_name = args.name
    if not base_name:
        base_name = os.path.splitext(os.path.basename(args.filename))[0]
        
    out_dir = args.dir
    if not out_dir:
        out_dir = DEFAULT_OUTPUT_DIR
        
    palette_mgr = PaletteManager()
    schem_parser = SchematicParser(args.filename, taglist, palette_mgr)

    if args.command == "part":
        if schem_parser.width != 16 or schem_parser.length != 16:
            print(f"Error: Part command requires exactly 16x16 schematic. Found: {schem_parser.width}x{schem_parser.length}")
            return
            
        print(f"Generating standalone part...")
        output_folder = os.path.join(out_dir, f"{base_name}")
        os.makedirs(output_folder, exist_ok=True)
        
        slices = schem_parser.generate_slice(0, 0, 0, schem_parser.height)
        part_json = {
            "xsize": 16,
            "zsize": 16,
            "palette": palette_mgr.to_dict(),
            "slices": slices
        }
        save_json(os.path.join(output_folder, f"{base_name}.json"), part_json)
        
    elif args.command == "building":
        if schem_parser.width != 16 or schem_parser.length != 16:
            print(f"Error: Building command requires exactly 16x16 schematic. Found: {schem_parser.width}x{schem_parser.length}")
            return
            
        print(f"Generating building...")
        output_folder = os.path.join(out_dir, f"{base_name}_building")
        
        palette_name = f"{base_name}_palette"
        building_json, parts = generate_building(
            parser=schem_parser,
            base_name=base_name,
            palette_name=palette_name,
            cellar_count=args.cellars,
            floor_count=args.floors,
            unique=args.unique,
            start_x=0,
            start_z=0,
            embedded_palette=False
        )
        
        save_json(os.path.join(output_folder, f"{base_name}_building.json"), building_json)
        for part in parts:
            save_json(os.path.join(output_folder, "parts", part["name"]), part["content"])
            
        save_json(os.path.join(output_folder, f"{palette_name}.json"), palette_mgr.to_dict())
        
    elif args.command == "multibuilding":
        # Missing blocks up to multiple of 16 are treated as air automatically by `get_char_for_block`
        dimx = math.ceil(schem_parser.width / 16.0)
        dimz = math.ceil(schem_parser.length / 16.0)
        
        print(f"Generating multibuilding ({dimx}x{dimz} chunks)...")
        output_folder = os.path.join(out_dir, f"{base_name}_multibuilding")
        
        palette_name = f"{base_name}_palette"
        building_matrix = []
        
        # Iterate chunks
        for x_idx in range(dimx):
            z_row = []
            for z_idx in range(dimz):
                chunk_name = f"{base_name}_{x_idx}_{z_idx}"
                z_row.append(f"{chunk_name}_building")
                
                building_json, parts = generate_building(
                    parser=schem_parser,
                    base_name=chunk_name,
                    palette_name=palette_name,
                    cellar_count=args.cellars,
                    floor_count=args.floors,
                    unique=args.unique,
                    start_x=x_idx * 16,
                    start_z=z_idx * 16,
                    embedded_palette=False
                )
                
                save_json(os.path.join(output_folder, "buildings", f"{chunk_name}_building.json"), building_json)
                for part in parts:
                    save_json(os.path.join(output_folder, "parts", part["name"]), part["content"])
                    
            building_matrix.append(z_row)
            
        multibuilding_json = {
            "dimx": dimx,
            "dimz": dimz,
            "buildings": building_matrix
        }
        save_json(os.path.join(output_folder, f"{base_name}_multibuilding.json"), multibuilding_json)
        save_json(os.path.join(output_folder, f"{palette_name}.json"), palette_mgr.to_dict())

if __name__ == "__main__":
    main()
