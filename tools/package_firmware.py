"""Create a distributable sector package, excluding boot and mutable user data."""
from pathlib import Path
import hashlib
import json

def sha(data):
    return hashlib.sha256(data).hexdigest()

def package(original, patched, loader, output):
    if len(original) != 0x80000 or len(patched) != 0x80000:
        raise ValueError('Expected 512 KiB images')
    if original[:0x2000] != patched[:0x2000] or original[0x67000:] != patched[0x67000:]:
        raise ValueError('Image changes boot data or mutable settings')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    sectors = []
    for offset in range(0, 0x80000, 4096):
        a, b = original[offset:offset + 4096], patched[offset:offset + 4096]
        if a == b:
            continue
        if not 0x2000 <= offset < 0x67000:
            raise ValueError('Patch sector outside static firmware')
        sectors.append({'offset': offset, 'size': 4096, 'data_offset': len(payload),
                        'original_sha256': sha(a), 'patched_sha256': sha(b)})
        payload.extend(b)
    filename = 'mivo-m82-usb-clock-v1.0.0.sectors.bin'
    manifest = {
        'format': 'mivo-m82-sector-bundle-v1', 'version': '1.0.0',
        'model': 'MIVO M82', 'platform': 'JieLi BR25 / AC696x',
        'flash_size': 0x80000, 'flash_id': 0xcd7013, 'chip_key': 0x077a,
        'source_static_sha256': sha(original[:0x67000]),
        'patched_static_sha256': sha(patched[:0x67000]),
        'bundle_file': filename, 'bundle_sha256': sha(payload),
        'ram_loader_sha256': sha(loader),
        'preserved_ranges': [[0, 0x2000], [0x67000, 0x80000]],
        'sectors': sectors,
        'compatibility': 'Only the exact original static-region hash and SFC key above are supported. No force mode.',
        'hardware_validation': 'USB SET/GET, clock display and audio confirmed on one unit on 2026-11-09.'}
    (output / filename).write_bytes(payload)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest
