from datetime import datetime
import time
from .protocol import decode_report, encode_set, ProtocolError

def synchronize(device, *, now=datetime.now, sleep=time.sleep, monotonic=time.monotonic, timeout=5):
    before = decode_report(device.get_feature())
    if before.status == 1:
        raise ProtocolError('RTC is not initialized in this device mode')
    if before.status == 2:
        raise ProtocolError('A previous SET request is still pending')
    # An earlier rejected SET (status 3) can be retried with a valid packet.
    device.set_feature(encode_set(now().replace(microsecond=0)))
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        sleep(.1)
        report = decode_report(device.get_feature())
        if report.status in (1, 3):
            raise ProtocolError('Firmware rejected SET or could not queue it in app_core')
        current = now()
        if report.status == 0 and report.time is not None:
            difference = (report.time - current).total_seconds()
            if abs(difference) <= 2:
                return {'before': before.time.isoformat(' ') if before.time else None,
                        'after': report.time.isoformat(' '), 'windows_local': current.isoformat(' '),
                        'difference_seconds': round(difference, 3), 'verified': True}
    raise ProtocolError('RTC update did not pass readback verification within the timeout')

def sync_clock():
    from .windows_hid import WindowsHID
    with WindowsHID().open_clock() as device:
        return synchronize(device)
