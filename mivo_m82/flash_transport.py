"""Windows SCSI transport to the pinned third-party BR25 RAM loader."""
import ctypes
import os
from pathlib import Path
import sys
import time
from .bundle import sha

def open_loader(path, manifest):
    if os.name != 'nt':
        raise OSError('Flashing currently supports Windows only')
    root = Path(__file__).resolve().parent.parent
    dependency = root / 'vendor/jl-uboot-tool'
    if not (dependency / 'jltech/uboot.py').is_file():
        raise RuntimeError('Run git submodule update --init --recursive and install requirements-flash.txt')
    sys.path.insert(0, str(dependency))
    from scsiio import win32port as w
    from scsiio.common import SCSIException
    from jltech.uboot import JL_UBOOT, JL_LoaderV2
    w.GENERIC_READ, w.GENERIC_WRITE = 0x80000000, 0x40000000
    w.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD,
                                 ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    class Device(w.SCSIDev):
        def execute(self, cdb, data_out, data_in, **_):
            opcode = cdb[0] if cdb[0] == 0x12 else int.from_bytes(cdb[:2], 'big')
            allowed = {0x12, 0xfb01, 0xfb04, 0xfb06, 0xfb08, 0xfc09,
                       0xfc0a, 0xfc0b, 0xfc0c, 0xfc14, 0xfd05, 0xfd07}
            if opcode not in allowed:
                raise RuntimeError(f'Blocked SCSI command 0x{opcode:04x}')
            s = w.SCSI_PASS_THROUGH_DIRECT()
            s.len = ctypes.sizeof(s)
            s.target_id, s.timeout, s.cdb_len = 1, 5, len(cdb)
            s.cdb[:len(cdb)] = cdb
            length = len(data_out) if data_out is not None else len(data_in) if data_in is not None else 0
            s.data_len = length
            s.dir = 0 if data_out is not None else 1 if data_in is not None else 2
            buf = ctypes.create_string_buffer(length) if length else None
            if data_out is not None:
                ctypes.memmove(buf, bytes(data_out), length)
            if length:
                s.data_ptr = ctypes.cast(buf, ctypes.POINTER(w.BYTE))
            returned = w.DWORD()
            ok = w.DeviceIoControl(self.fhandle, w.IOCTL_SCSI_PASS_THROUGH_DIRECT,
                                  ctypes.byref(s), s.len, ctypes.byref(s), s.len,
                                  ctypes.byref(returned), None)
            if not ok:
                raise SCSIException(str(ctypes.WinError()))
            if s.status or s.data_len != length:
                raise SCSIException(f'SCSI status={s.status}, transfer={s.data_len}/{length}')
            if data_in is not None:
                data_in[:] = buf.raw[:length]
            return 0
    def inquiry(device):
        data = bytearray(36)
        device.execute(bytes.fromhex('120000002400'), None, data)
        return bytes(data[8:16]).decode().strip(), bytes(data[16:32]).decode().strip()
    device = Device(path)
    try:
        vendor, product = inquiry(device)
        if vendor != 'BR25' or product not in ('UDISK', 'UBOOT1.00'):
            raise RuntimeError(f'Not the expected BR25 device: {vendor}/{product}')
        if product == 'UDISK':
            print('Entering BR25 USB bootloader', flush=True)
            try:
                JL_LoaderV2(device).online_device()
            except (SCSIException, AssertionError):
                pass  # The expected transition can disconnect the transport.
            device.close()
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    device = Device(path)
                    if inquiry(device) == ('BR25', 'UBOOT1.00'):
                        break
                    device.close()
                except (OSError, SCSIException):
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError('BR25 USB bootloader did not appear')
        blob = (dependency / 'data/loaderblobs/usb/br25loader.bin').read_bytes()
        if sha(blob) != manifest['ram_loader_sha256']:
            raise RuntimeError('Unexpected RAM loader checksum')
        rom = JL_UBOOT(device)
        # BR25 memory-rw-mengli-crypt=True: pass the stored encoded loader as-is.
        for offset in range(0, len(blob), 512):
            rom.mem_write(0x12000 + offset, blob[offset:offset + 512])
        rom.mem_jump(0x12000, 1)
        loader = JL_LoaderV2(device)
        if loader.online_device() != {'type': 3, 'id': manifest['flash_id']}:
            raise RuntimeError('Unexpected flash type or ID')
        if loader.chip_key() != manifest['chip_key']:
            raise RuntimeError('Incompatible SFC chip key')
        return device, loader
    except BaseException:
        device.close()
        raise
