import json
from pathlib import Path
import tempfile
import unittest
from mivo_m82.bundle import FirmwareBundle, FLASH_SIZE, sha, write_verified

class NOR:
    def __init__(self, data, fail=False):
        self.data = bytearray(data); self.fail = fail; self.erases = []
    def flash_read(self, offset, size): return bytes(self.data[offset:offset + size])
    def flash_erase_sector(self, offset):
        self.erases.append(offset)
        self.data[offset:offset + 4096] = b'\xff' * 4096
    def flash_write(self, offset, data):
        if self.fail and len(self.erases) == 2:
            self.fail = False
            raise IOError('injected program failure')
        if not all((a & b) == b for a, b in zip(self.data[offset:offset + len(data)], data)):
            raise IOError('attempted NOR 0-to-1 programming without erase')
        self.data[offset:offset + len(data)] = data

class FlashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        original = bytearray(b'\xff' * FLASH_SIZE)
        original[0x70000] = 42
        self.original = bytes(original)
        patched = bytearray(original)
        sectors = []; payload = bytearray()
        for offset, fill in [(0x2000, 0xa1), (0x34000, 0x42), (0x5c000, 0x35)]:
            data = bytes([fill]) * 4096
            sectors.append({'offset': offset, 'size': 4096, 'data_offset': len(payload),
                            'original_sha256': sha(original[offset:offset + 4096]), 'patched_sha256': sha(data)})
            patched[offset:offset + 4096] = data; payload.extend(data)
        self.patched = bytes(patched)
        (root / 'payload.bin').write_bytes(payload)
        self.manifest = {'format': 'mivo-m82-sector-bundle-v1', 'flash_size': FLASH_SIZE,
            'bundle_file': 'payload.bin', 'bundle_sha256': sha(payload), 'sectors': sectors,
            'source_static_sha256': sha(original[:0x67000]), 'patched_static_sha256': sha(patched[:0x67000])}
        self.path = root / 'manifest.json'
        self.path.write_text(json.dumps(self.manifest))
        self.bundle = FirmwareBundle(self.path)
    def tearDown(self): self.temp.cleanup()
    def test_apply_preserves_boot_and_current_settings(self):
        fresh = bytearray(self.original); fresh[0x71000] = 77
        target = self.bundle.apply_to(fresh)
        device = NOR(fresh)
        write_verified(device, bytes(fresh), target, self.bundle, lambda _: None)
        self.assertEqual(bytes(device.data), target)
        self.assertEqual(device.data[:0x2000], fresh[:0x2000])
        self.assertEqual(device.data[0x67000:], fresh[0x67000:])
    def test_failure_rolls_back_every_touched_sector(self):
        device = NOR(self.original, fail=True)
        with self.assertRaisesRegex(IOError, 'injected'):
            write_verified(device, self.original, self.patched, self.bundle, lambda _: None)
        self.assertEqual(bytes(device.data), self.original)
    def test_restore_preserves_new_pairings(self):
        fresh = bytearray(self.patched); fresh[0x71000] = 11
        target = self.bundle.restore_to(fresh, self.original)
        self.assertEqual(target[:0x67000], self.original[:0x67000])
        self.assertEqual(target[0x67000:], fresh[0x67000:])
    def test_unknown_revision_is_rejected_before_erase(self):
        unknown = bytearray(self.original); unknown[0x30000] = 3
        device = NOR(unknown)
        with self.assertRaises(ValueError):
            write_verified(device, bytes(unknown), self.patched, self.bundle, lambda _: None)
        self.assertEqual(device.erases, [])
    def test_boot_or_settings_sector_is_rejected(self):
        for offset in (0, 0x1000, 0x67000, 0x7e000):
            m = json.loads(json.dumps(self.manifest)); m['sectors'][0]['offset'] = offset
            self.path.write_text(json.dumps(m))
            with self.subTest(offset=offset), self.assertRaises(ValueError): FirmwareBundle(self.path)
    def test_payload_corruption_is_rejected(self):
        payload = self.path.parent / 'payload.bin'
        data = bytearray(payload.read_bytes()); data[-1] ^= 1; payload.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'SHA-256'): FirmwareBundle(self.path)
    def test_actual_published_bundle(self):
        bundle = FirmwareBundle()
        self.assertEqual(len(bundle.sectors), 13)
        self.assertTrue(all(0x2000 <= s.offset < 0x67000 for s in bundle.sectors))

if __name__ == '__main__':
    unittest.main()
