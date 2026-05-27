import os
import shutil
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from amulet_nbt import load
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

INPUT_DIR = r""
ARCHIVE_DIR = r""
OUTPUT_DIR = r""

# make sure dirs exist
for d in [INPUT_DIR, ARCHIVE_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

symbols = list(
    "αβγδεζηθικλμνξοπρστυφχψω"          # Greek lowercase
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"          # Greek uppercase
    "∑∆∏∫√∞≈≠≤≥∧∨⊂⊃⊆⊇⊕⊗⊥∴∵∠∡⊾≅≡∝∂∇ℵℶℷℸ"  # Math & logic symbols
    "ЖДФИЛПЦЧШЩЭЮЯ"                     # Cyrillic uppercase
    "ぁあぃいぅうぇえぉお"               # Japanese Hiragana vowels
    "かきくけこさしすせそ"               # Hiragana consonants 1
    "たちつてとなにぬねの"               # Hiragana consonants 2
    "まみむめも"                         # Hiragana consonants 3
    "אבגדהוזחטיכלמנסעפצקרשת"           # Hebrew alphabet
    "अआइईउऊऋऌएऐओऔकखगघङचछज"            # Hindi (Devanagari) selection
    "한글ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"    # Korean Hangul jamo
    "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธน"       # Thai
    "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ" # Georgian
    "ԱԲԳԴԵԶԷԸԹԺԻԼԽԾԿՀՁՂՃՄՅՆՇՈՉՊՋՌՍՎՏՐՑՈւՓՔևՕՖ" # Armenian
    "அஆஇஈஉஊஎஏஐஒஓஔகஙசஞடணதநபமயரலவழளறனஷஸஹ" # Tamil
    "ກຂຄງຈຊຍດຕນບປຜຝພຟມຢຣລວສຫຬອຮ"           # Lao
    "ሀሁሂሃሄህሆለሉሊላሌልሎመሙሚማሜምሞ"             # Ethiopic
    "ᎠᎡᎢᎣᎤᎥᎦᎧᎨᎩᎪᎫᎬᎭᎮᎯᎰᎱᎲᎳᎴᎵᎶᎷ"         # Cherokee
    "ཀཁགངཅཆཇཉཏཐདནཙཚཛཝཞཟའཡརལཤཥསཧཨ"         # Tibetan
)

def schem_to_slices(path, json_path):
    # load schematic
    nbt = load(path)
    width = int(nbt["Width"])
    height = int(nbt["Height"])
    length = int(nbt["Length"])
    palette = {v.value: k for k, v in nbt["Palette"].items()}  # id->block
    blockdata = nbt["BlockData"].value

    palette_map = {" ": "minecraft:air"}  # always reserve " " for air
    char_list = iter(symbols)

    slices = []
    index = 0
    for y in range(height):
        layer = []
        for z in range(length):
            row = ""
            for x in range(width):
                block_id = blockdata[index]
                block_name = palette[block_id]
                index += 1

                if block_name == "minecraft:air":
                    row += " "
                else:
                    # assign a new symbol if needed
                    if block_name not in palette_map.values():
                        try:
                            new_char = next(char_list)
                        except StopIteration:
                            raise RuntimeError("Ran out of unique symbols for palette!")
                        palette_map[new_char] = block_name
                    # find char for this block
                    for k, v in palette_map.items():
                        if v == block_name:
                            row += k
                            break
            layer.append(row)
        slices.append(layer)

    # build final JSON
    out = {
        "xsize": width,
        "zsize": length,
        "palette": {"palette": [{"char": k, "block": v} for k, v in palette_map.items()]},
        "slices": slices
    }

    # write to file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
    print(f"Exported: {json_path}")

class SchemHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".schem"):
            fname = os.path.basename(event.src_path)
            archive_path = os.path.join(ARCHIVE_DIR, fname)
            json_path = os.path.join(OUTPUT_DIR, fname.replace(".schem", ".json"))

            # copy to archive
            shutil.copy2(event.src_path, archive_path)
            print(f"Archived {fname}")

            # convert to JSON
            try:
                schem_to_slices(archive_path, json_path)
                print(f"Successfully Converted {fname} -> {json_path}")
            except Exception as e:
                print(f"Error converting {fname}: {e}")

if __name__ == "__main__":
    observer = Observer()
    handler = SchemHandler()
    observer.schedule(handler, INPUT_DIR, recursive=False)
    observer.start()
    print("\n--------------------------")
    print(f"Watching folder: {INPUT_DIR}")
    print("\n--------------------------")
    try:
        input("Press Enter to Quit.\n")
        observer.stop()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()