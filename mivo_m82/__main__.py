import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description='MIVO M82 USB clock utility')
    parser.add_argument('command', choices=['read', 'sync', 'install-autostart', 'uninstall-autostart', 'autostart'])
    args = parser.parse_args()
    try:
        if args.command == 'sync':
            from .sync import sync_clock
            result = sync_clock()
        elif args.command == 'read':
            from .windows_hid import WindowsHID
            from .protocol import decode_report
            with WindowsHID().open_clock() as device:
                report = decode_report(device.get_feature())
            result = {'rtc': report.time.isoformat(' ') if report.time else None, 'status': report.status}
        else:
            from . import autostart
            if args.command == 'autostart':
                autostart.run()
                return 0
            result = autostart.install() if args.command == 'install-autostart' else autostart.uninstall()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
