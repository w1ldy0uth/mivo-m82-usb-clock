from datetime import datetime
import struct
import unittest
from mivo_m82.protocol import encode_set, decode_report, ProtocolError

def response(value=datetime(2026, 11, 9, 16, 37, 43), status=0):
    return b'\0M82T\x02' + bytes([status]) + struct.pack(
        '<HBBBBB', value.year, value.month, value.day, value.hour, value.minute, value.second) + b'\0' * 3

class ProtocolTests(unittest.TestCase):
    def test_set_wire_layout(self):
        self.assertEqual(encode_set(datetime(2026, 11, 9, 16, 37, 43)),
                         bytes.fromhex('004d3832540101ea070b0910252b000000'))
    def test_decode_verified_hardware_sample(self):
        report = decode_report(response())
        self.assertEqual(report.time, datetime(2026, 11, 9, 16, 37, 43))
        self.assertEqual(report.status, 0)
    def test_uninitialized_rtc_has_no_date(self):
        report = decode_report(b'\0M82T\x02\x01' + b'\0' * 10)
        self.assertIsNone(report.time)
    def test_reject_wrong_device_payload_and_short_data(self):
        for data in (b'', response()[:-1], b'\0FAIL' + response()[5:]):
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                decode_report(data)
    def test_reject_unknown_status(self):
        with self.assertRaises(ProtocolError):
            decode_report(response(status=8))
    def test_reject_unsupported_year(self):
        for year in (1999, 2100):
            with self.subTest(year=year), self.assertRaises(ValueError):
                encode_set(datetime(year, 1, 1))
    def test_reject_corrupt_returned_date(self):
        bad = bytearray(response()); bad[9] = 0
        with self.assertRaises(ProtocolError):
            decode_report(bad)

if __name__ == '__main__':
    unittest.main()
