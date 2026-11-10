"""Platform-independent encoding of the M82 HID Feature Report."""
from dataclasses import dataclass
from datetime import datetime
import struct

REPORT_LENGTH = 17
MAGIC = b'M82T'

class ProtocolError(RuntimeError):
    pass

@dataclass(frozen=True)
class ClockReport:
    time: datetime | None
    status: int

def encode_set(value: datetime) -> bytes:
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    if not 2000 <= value.year <= 2099:
        raise ValueError('The firmware supports RTC years 2000 through 2099')
    return b'\0' + MAGIC + b'\x01\x01' + struct.pack(
        '<HBBBBB', value.year, value.month, value.day,
        value.hour, value.minute, value.second) + b'\0' * 3

def decode_report(data: bytes) -> ClockReport:
    if len(data) != REPORT_LENGTH or data[:6] != b'\0M82T\x02':
        raise ProtocolError('Not an M82 USB clock Feature Report')
    status = data[6]
    if status not in (0, 1, 2, 3):
        raise ProtocolError(f'Unknown firmware status: {status}')
    if status == 1:
        return ClockReport(None, status)
    try:
        value = datetime(*struct.unpack_from('<HBBBBB', data, 7))
    except ValueError as exc:
        raise ProtocolError(f'Invalid RTC date in response: {exc}') from exc
    return ClockReport(value, status)
