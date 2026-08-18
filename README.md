# Schematic to Lost Cities Converter

This is a CLI tool (`main.py`) that converts Minecraft `.schem` files (specifically from WorldEdit Forge 1.20.1) into structured `.json` parts used by the Lost Cities mod.

## Prerequisites

- Python 3.x (Fully compatible with Python 3.14+)
- Dependencies: `nbtlib`, `beartype`

## Features

- **Chunking System**: Automatically cuts massively oversized schematics into 16x16 X/Z chunks.
- **Vertical Auto-Slicing**: Automatically splits 6-block heights for cellars, ground, and multiple floors, with any remainder automatically becoming the `top` section.
- **NBT Tag Preservation**: Retains internal block entity data (like chest inventories or command blocks) in your custom Lost Cities palette using a block whitelist.
- **Dynamic Palette Generator**: Dynamically generates valid UTF-8 symbols mapping exactly to your unique combinations of blocks and NBT states.

## Usage

```bash
python main.py [-h] {part,building,multibuilding} <filename> [options]
```

### Commands

#### 1. `part`
Converts a strict 16x16 footprint `.schem` into a single standalone `.json` part file with an embedded palette.

```bash
python main.py part my_statue.schem -d ./output
```

#### 2. `building`
Splits a 16x16 footprint `.schem` vertically into its Lost Cities structural components (cellars, ground, floors, and top).

**Flags:**
- `-c`, `--cellars`: Number of 6-block tall cellars.
- `-f`, `--floors`: Number of 6-block tall floors above ground.
- `-u`, `--unique`: Forces parts to generate with their strict `floor: X` parameters rather than generating generic, interchangeable variants.

```bash
python main.py building skyscraper.schem -c 2 -f 5 -u
```

#### 3. `multibuilding`
Chunks any `.schem` exceeding 16x16 bounds into an X/Z grid matrix of building clusters, then processes them individually. Empty chunk space is intelligently padded with `minecraft:air`.

```bash
python main.py multibuilding massive_city_block.schem -c 1 -f 3
```

### Shared Options

- `-d`, `--dir`: Target output directory for JSON generation (defaults to your OS Downloads folder).
- `--name`: Provide a custom naming prefix (defaults to the schematic filename).
- `--taglist`: Comma-separated block ID whitelist to retain NBT parameters.
  - *Example*: `--taglist "minecraft:chest,minecraft:command_block"`
