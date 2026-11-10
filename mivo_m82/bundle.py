"""Validated sector package; never contains the device's mutable settings."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

FLASH_SIZE = 0x80000
SECTOR_SIZE = 0x1000
STATIC_END = 0x67000
DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / 'firmware/manifest.json'

def sha(data):
    return hashlib.sha256(data).hexdigest()

@dataclass(frozen=True)
class Sector:
    offset: int
    original_sha256: str
    data: bytes

class FirmwareBundle:
    def __init__(self, path=DEFAULT_MANIFEST):
        path = Path(path)
        self.manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        m = self.manifest
        if m.get('format') != 'mivo-m82-sector-bundle-v1' or m.get('flash_size') != FLASH_SIZE:
            raise ValueError('Unsupported firmware bundle format or flash size')
        payload_path = path.parent / m['bundle_file']
        if payload_path.resolve().parent != path.parent.resolve():
            raise ValueError('The bundle must be in the same directory as the manifest')
        payload = payload_path.read_bytes()
        if sha(payload) != m['bundle_sha256']:
            raise ValueError('Firmware bundle SHA-256 mismatch')
        sectors = []
        for index, item in enumerate(m['sectors']):
            offset = item['offset']
            if offset % SECTOR_SIZE or not 0x2000 <= offset < STATIC_END:
                raise ValueError('Sector would overlap boot data or mutable settings')
            if item['data_offset'] != index * SECTOR_SIZE or item['size'] != SECTOR_SIZE:
                raise ValueError('Invalid sector package layout')
            data = payload[index * SECTOR_SIZE:(index + 1) * SECTOR_SIZE]
            if len(data) != SECTOR_SIZE or sha(data) != item['patched_sha256']:
                raise ValueError('Patched sector checksum mismatch')
            sectors.append(Sector(offset, item['original_sha256'], data))
        if not sectors or len({s.offset for s in sectors}) != len(sectors):
            raise ValueError('Empty or duplicate sector list')
        if len(payload) != len(sectors) * SECTOR_SIZE:
            raise ValueError('Unexpected trailing data in sector bundle')
        self.sectors = tuple(sectors)

    def validate_current(self, image):
        if len(image) != FLASH_SIZE:
            raise ValueError('Expected a 512 KiB flash image')
        prefix = sha(image[:STATIC_END])
        if prefix not in (self.manifest['source_static_sha256'], self.manifest['patched_static_sha256']):
            raise ValueError('Unsupported firmware revision: immutable-region hash does not match; nothing will be erased')

    def apply_to(self, current):
        self.validate_current(current)
        target = bytearray(current)
        for sector in self.sectors:
            target[sector.offset:sector.offset + SECTOR_SIZE] = sector.data
        if sha(target[:STATIC_END]) != self.manifest['patched_static_sha256']:
            raise ValueError('Resulting firmware static-region checksum mismatch')
        return bytes(target)

    def restore_to(self, current, backup):
        self.validate_current(current)
        if len(backup) != FLASH_SIZE or sha(backup[:STATIC_END]) != self.manifest['source_static_sha256']:
            raise ValueError('Restore requires a compatible ORIGINAL pre-install backup')
        target = bytearray(current)
        for sector in self.sectors:
            target[sector.offset:sector.offset + SECTOR_SIZE] = backup[sector.offset:sector.offset + SECTOR_SIZE]
        if sha(target[:STATIC_END]) != self.manifest['source_static_sha256']:
            raise ValueError('Restored code checksum mismatch')
        return bytes(target)

class RollbackError(RuntimeError):
    """Keep USB bootloader powered and retry restoration; do not reset."""

def read_flash(loader, address=0, length=FLASH_SIZE):
    if address < 0 or length < 0 or address + length > FLASH_SIZE:
        raise ValueError('Read outside flash')
    result = bytearray()
    for offset in range(address, address + length, 256):
        count = min(256, address + length - offset)
        data = loader.flash_read(offset, count)
        if len(data) != count:
            raise IOError('Short flash read')
        result.extend(data)
    return bytes(result)

def program_sector(loader, offset, data):
    if offset % SECTOR_SIZE or not 0x2000 <= offset < STATIC_END or len(data) != SECTOR_SIZE:
        raise ValueError('Write outside the allowed firmware sectors')
    loader.flash_erase_sector(offset)
    for i in range(0, SECTOR_SIZE, 256):
        loader.flash_write(offset + i, data[i:i + 256])
    if read_flash(loader, offset, SECTOR_SIZE) != data:
        raise IOError(f'Sector readback mismatch at 0x{offset:05x}')

def write_verified(loader, current, target, bundle, progress=print):
    bundle.validate_current(current)
    if len(target) != FLASH_SIZE:
        raise ValueError('Invalid target image length')
    allowed = {s.offset for s in bundle.sectors}
    changed = [o for o in range(0, FLASH_SIZE, SECTOR_SIZE)
               if current[o:o + SECTOR_SIZE] != target[o:o + SECTOR_SIZE]]
    if not set(changed) <= allowed:
        raise ValueError('Target changes sectors outside the bundle')
    # Write resources first, entry hook next, filesystem/header sector last.
    order = [o for o in changed if o not in (0x2000, 0x34000)]
    order += [o for o in (0x34000, 0x2000) if o in changed]
    dirty = []
    try:
        for offset in order:
            dirty.append(offset)
            progress(f'Programming and verifying sector 0x{offset:05x}')
            program_sector(loader, offset, target[offset:offset + SECTOR_SIZE])
        if read_flash(loader) != target:
            raise IOError('Full flash readback mismatch')
    except BaseException as exc:
        progress('Write failed; restoring touched sectors from fresh backup')
        try:
            for offset in reversed(dirty):
                program_sector(loader, offset, current[offset:offset + SECTOR_SIZE])
            if read_flash(loader) != current:
                raise IOError('Rollback readback mismatch')
        except BaseException as restore_error:
            raise RollbackError(f'Rollback failed: {restore_error}. Keep the device powered in USB bootloader mode.') from exc
        progress('ROLLBACK VERIFIED')
        raise
    return order
