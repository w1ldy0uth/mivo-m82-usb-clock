"""Rebuild locally from a compatible private original dump. Never flash automatically."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import struct
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from assemble import assemble
from package_firmware import package

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    args = parser.parse_args()
    original_path = args.original.resolve()
    raw = original_path.read_bytes()
    manifest = json.loads((ROOT / 'firmware/manifest.json').read_text())
    if len(raw) != 0x80000 or hashlib.sha256(raw[:0x67000]).hexdigest() != manifest['source_static_sha256']:
        raise ValueError('This is not the compatible ORIGINAL static firmware revision')
    code = assemble()
    build = ROOT / 'build'
    # Upstream creates a new output directory; use a unique private build dir.
    import tempfile
    unpacked = Path(tempfile.mkdtemp(prefix='unpack-', dir=build)) / 'firmware'
    sys.path.insert(0, str(ROOT / 'vendor/jl-misctools/firmware'))
    old_argv = sys.argv[:]
    try:
        sys.argv = ['fwunpack_newfw.py', '--dirname', str(unpacked), str(original_path)]
        runpy.run_path(str(ROOT / 'vendor/jl-misctools/firmware/fwunpack_newfw.py'), run_name='__main__')
    finally:
        sys.argv = old_argv
    from jltech.cipher import jl_sfc_cipher
    from jltech.crc import jl_crc16
    from pi32v2isa import asm, elf
    plain = bytearray((unpacked / 'decrypted.bin').read_bytes())
    app = (unpacked / 'files/app.bin').read_bytes()
    if app[0x46554:0x46554 + 50] != bytes.fromhex((ROOT / 'firmware/hid-input-prefix.hex').read_text()):
        raise ValueError('Unexpected original HID descriptor')
    start, end, app_start, app_end = 0x2000, 0x66746, 0x2100, 0x5c9c6
    check = bytearray(plain)
    jl_sfc_cipher(check, start, end - start, start, 0x077a)
    if check[start:end] != raw[start:end]:
        raise ValueError('Baseline SFC round-trip failed')
    delta = (len(code) + 31) & ~31
    if end + delta > 0x67000 or any(x != 255 for x in raw[end:end + delta]):
        raise ValueError('Insufficient verified space before settings')
    modified = bytearray(plain)
    modified[app_end + delta:end + delta] = plain[app_end:end]
    modified[app_end:app_end + delta] = code + b'\xff' * (delta - len(code))
    def instruction(text):
        obj = elf.read(asm.assemble_source('.text\n' + text + '\n'))
        return bytes(next(s for s in obj.sections if s.name == '.text').data)
    hook = 0x34d2a
    if modified[hook:hook + 4].hex() != '76040415':
        raise ValueError('Unexpected HID entry prologue')
    jump = instruction(f'goto {0x1e5a9c6 - (0x1e32d2a + 4)}')
    if len(jump) != 4:
        raise ValueError('Unexpected entry jump size')
    modified[hook:hook + 4] = jump
    if modified[0x3493e:0x34940].hex() != '4833':
        raise ValueError('Unexpected configuration descriptor length instruction')
    length = instruction('r0 = 67')
    if len(length) != 2:
        raise ValueError('Unexpected descriptor length instruction size')
    modified[0x3493e:0x34940] = length
    if modified[0x2118:0x211e].hex() != 'c2ffe8420000':
        raise ValueError('Unexpected BSS initialization')
    struct.pack_into('<I', modified, 0x211a, 0x4300)
    def header_crc(offset):
        struct.pack_into('<H', modified, offset, jl_crc16(modified[offset + 2:offset + 32]))
    new_length = app_end + delta - app_start
    struct.pack_into('<H', modified, 0x2022, jl_crc16(modified[app_start:app_start + new_length]))
    struct.pack_into('<I', modified, 0x2028, new_length)
    header_crc(0x2020)
    struct.pack_into('<H', modified, 0x2002, jl_crc16(modified[0x2020:app_end + delta]))
    struct.pack_into('<I', modified, 0x2008, app_end + delta - 0x2000)
    header_crc(0x2000)
    encoded = bytearray(modified)
    jl_sfc_cipher(encoded, start, end + delta - start, start, 0x077a)
    output = bytearray(raw)
    output[start:end + delta] = encoded[start:end + delta]
    check = bytearray(output)
    jl_sfc_cipher(check, start, end + delta - start, start, 0x077a)
    if check[start:end + delta] != modified[start:end + delta]:
        raise ValueError('Patched SFC round-trip failed')
    (build / 'patched-private-image.bin').write_bytes(output)
    loader = (ROOT / 'vendor/jl-uboot-tool/data/loaderblobs/usb/br25loader.bin').read_bytes()
    rebuilt = package(raw, output, loader, build / 'firmware')
    print('Rebuilt sector package:', rebuilt['bundle_sha256'])
    print('Matches published package:', rebuilt['bundle_sha256'] == manifest['bundle_sha256'])
    print('Private full image stays in ignored build/; it is not a vendor update package.')

if __name__ == '__main__':
    main()
