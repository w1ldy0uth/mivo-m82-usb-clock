from datetime import datetime
import unittest
from mivo_m82.protocol import ProtocolError
from mivo_m82.sync import synchronize
from test_protocol import response

class Clock:
    def __init__(self): self.value = 0
    def monotonic(self): return self.value
    def sleep(self, delay): self.value += delay
    def now(self): return datetime(2026, 11, 9, 16, 37, 43, 500000)

class Device:
    def __init__(self, reports): self.reports = iter(reports); self.writes = []
    def get_feature(self): return next(self.reports)
    def set_feature(self, data): self.writes.append(data)

class SyncTests(unittest.TestCase):
    def run_sync(self, device):
        clock = Clock()
        return synchronize(device, now=clock.now, sleep=clock.sleep,
                           monotonic=clock.monotonic, timeout=.4)
    def test_waits_for_application_and_checks_readback(self):
        old = response(datetime(2024, 5, 5, 18, 30, 33))
        device = Device([old, response(status=2), response()])
        result = self.run_sync(device)
        self.assertTrue(result['verified'])
        self.assertEqual(result['difference_seconds'], -.5)
        self.assertEqual(len(device.writes), 1)
    def test_rejected_request_does_not_report_success(self):
        with self.assertRaises(ProtocolError):
            self.run_sync(Device([response(), response(status=3)]))
    def test_stale_time_does_not_report_success(self):
        old = response(datetime(2024, 5, 5))
        with self.assertRaises(ProtocolError):
            self.run_sync(Device([old] * 10))
    def test_can_retry_a_previous_rejection(self):
        result = self.run_sync(Device([response(status=3), response()]))
        self.assertTrue(result['verified'])
    def test_does_not_overwrite_a_pending_request(self):
        device = Device([response(status=2)])
        with self.assertRaises(ProtocolError): self.run_sync(device)
        self.assertEqual(device.writes, [])

if __name__ == '__main__':
    unittest.main()
