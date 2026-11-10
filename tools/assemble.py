"""Assemble the proven PI32v2 USB handler, without accessing a device."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent.parent

def assemble():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / 'vendor/pi32v2-isa'))
    from pi32v2isa import asm, elf, ld
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    prefix = bytes.fromhex((ROOT / 'firmware/hid-input-prefix.hex').read_text())
    (build / 'hid-prefix.bin').write_bytes(prefix)
    obj = asm.assemble_source((ROOT / 'firmware/usb_clock.s').read_text(), 'firmware/usb_clock.s')
    (build / 'usb_clock.o').write_bytes(obj)
    opts = ld.parse_args(['-T', 'firmware/usb_clock.ld', '-Map', 'build/usb_clock.map',
                          'build/usb_clock.o', '-o', 'build/usb_clock.elf'])
    linker, data = ld.link(opts)
    if data is None or linker.errors:
        raise RuntimeError('PI32v2 link failed: ' + '; '.join(linker.errors))
    (build / 'usb_clock.elf').write_bytes(data)
    (build / 'usb_clock.map').write_text(linker.map_text())
    section = next(s for s in elf.read(data).sections if s.name == '.text')
    if section.addr != 0x1e5a9c6:
        raise ValueError('Unexpected code link address')
    (build / 'usb_clock.bin').write_bytes(section.data)
    return bytes(section.data)

if __name__ == '__main__':
    print(f'Assembled {len(assemble())} bytes')
