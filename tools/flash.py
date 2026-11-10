"""Backup, guarded sector installation, and restoration. Run from an elevated terminal."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mivo_m82.bundle import FirmwareBundle, FLASH_SIZE, RollbackError, read_flash, sha, write_verified

def find_device():
    command = ("$d=@(Get-CimInstance Win32_DiskDrive | Where-Object { "
               "$_.PNPDeviceID -match '^USBSTOR\\\\DISK&VEN_BR25&PROD_(UDISK|UBOOT1.00)' }); "
               "if($d.Count -ne 1){throw 'Expected exactly one BR25 UDISK/UBOOT device'}; "
               "$d[0].DeviceID")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['backup', 'apply', 'restore'])
    p.add_argument('--device', help=r'Optional explicit device, e.g. \\.\PHYSICALDRIVE2')
    p.add_argument('--backup', type=Path, help='Original .bin backup to restore')
    p.add_argument('--backup-dir', type=Path, default=ROOT / 'backups')
    p.add_argument('--manifest', type=Path, default=ROOT / 'firmware/manifest.json')
    args = p.parse_args()
    from mivo_m82.flash_transport import open_loader
    bundle = FirmwareBundle(args.manifest)
    if args.mode == 'restore' and not args.backup:
        p.error('restore requires --backup ORIGINAL.bin')
    device_path = args.device or find_device()
    print('Target:', device_path, flush=True)
    device, loader = open_loader(device_path, bundle.manifest)
    safe_to_reset = True
    try:
        first, second = read_flash(loader), read_flash(loader)
        if first != second:
            raise IOError('The two fresh backup reads differ; no flash writes performed')
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = args.backup_dir / f'MIVO-M82-before-{args.mode}-{stamp}.bin'
        with backup.open('xb') as stream:
            stream.write(first)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        if backup.read_bytes() != first:
            raise IOError('Saved backup verification failed')
        metadata = {'size': FLASH_SIZE, 'sha256': sha(first), 'mode': args.mode,
                    'compatible_original': sha(first[:0x67000]) == bundle.manifest['source_static_sha256']}
        backup.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(f'BACKUP: {backup}\nSHA256: {sha(first)}', flush=True)
        if args.mode == 'backup':
            return 0
        if args.mode == 'apply':
            target = bundle.apply_to(first)
        else:
            original = args.backup.read_bytes()
            expected = json.loads(args.backup.with_suffix('.json').read_text(encoding='utf-8-sig'))
            if sha(original) != expected['sha256']:
                raise ValueError('Original backup checksum mismatch')
            target = bundle.restore_to(first, original)
        written = write_verified(loader, first, target, bundle)
        print(f'FULL READBACK VERIFIED: {sha(target)}; sectors written: {len(written)}', flush=True)
        return 0
    except RollbackError:
        safe_to_reset = False
        raise
    finally:
        if safe_to_reset:
            try:
                loader.run_app(1)
            except Exception as exc:
                print(f'Application reset/disconnect: {exc}', flush=True)
        device.close()

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
