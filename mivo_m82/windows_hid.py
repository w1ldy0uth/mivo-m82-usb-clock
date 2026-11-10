"""Windows system HID API only; no hidapi DLL or audio driver replacement."""
import ctypes as c
from ctypes import wintypes as w
import os

class DeviceNotFound(RuntimeError):
    pass

class GUID(c.Structure):
    _fields_ = [('a', w.DWORD), ('b', w.WORD), ('c', w.WORD), ('d', w.BYTE * 8)]

class CAPS(c.Structure):
    _fields_ = [(n, w.USHORT) for n in (
        'Usage', 'UsagePage', 'InputReportByteLength', 'OutputReportByteLength',
        'FeatureReportByteLength')] + [('Reserved', w.USHORT * 17)] + [
        (n, w.USHORT) for n in ('NumberLinkCollectionNodes',
        'NumberInputButtonCaps', 'NumberInputValueCaps', 'NumberInputDataIndices',
        'NumberOutputButtonCaps', 'NumberOutputValueCaps', 'NumberOutputDataIndices',
        'NumberFeatureButtonCaps', 'NumberFeatureValueCaps', 'NumberFeatureDataIndices')]

class WindowsHID:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('The USB utility currently supports Windows only')
        self.h = c.WinDLL('hid', use_last_error=True)
        self.k = c.WinDLL('kernel32', use_last_error=True)
        self.cfg = c.WinDLL('cfgmgr32')
        self.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        self.k.CreateFileW.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.h.HidD_GetHidGuid.argtypes = [c.POINTER(GUID)]
        self.h.HidD_GetPreparsedData.argtypes = [w.HANDLE, c.POINTER(c.c_void_p)]
        self.h.HidD_GetPreparsedData.restype = c.c_ubyte
        self.h.HidD_FreePreparsedData.argtypes = [c.c_void_p]
        self.h.HidP_GetCaps.argtypes = [c.c_void_p, c.POINTER(CAPS)]
        self.h.HidP_GetCaps.restype = c.c_long
        for name in ('HidD_GetFeature', 'HidD_SetFeature'):
            fn = getattr(self.h, name)
            fn.argtypes = [w.HANDLE, c.c_void_p, w.ULONG]
            fn.restype = c.c_ubyte
        self.cfg.CM_Get_Device_Interface_List_SizeW.argtypes = [c.POINTER(w.ULONG), c.POINTER(GUID), w.LPCWSTR, w.ULONG]
        self.cfg.CM_Get_Device_Interface_ListW.argtypes = [c.POINTER(GUID), w.LPCWSTR, w.LPWSTR, w.ULONG, w.ULONG]

    def paths(self):
        guid = GUID()
        self.h.HidD_GetHidGuid(c.byref(guid))
        # Device interfaces can change while enumerating. Retry a size race.
        for _ in range(3):
            size = w.ULONG()
            result = self.cfg.CM_Get_Device_Interface_List_SizeW(c.byref(size), c.byref(guid), None, 0)
            if result:
                raise OSError(f'CM_Get_Device_Interface_List_SizeW: {result}')
            buf = c.create_unicode_buffer(max(size.value, 1))
            result = self.cfg.CM_Get_Device_Interface_ListW(c.byref(guid), None, buf, len(buf), 0)
            if result == 0:
                return [p for p in buf[:].split('\0') if 'vid_4c4a&pid_4155&mi_03' in p.lower()]
        raise OSError(f'HID interface enumeration failed: {result}')

    def open_clock(self):
        handles = []
        try:
            for path in self.paths():
                handle = self.k.CreateFileW(path, 0, 3, None, 3, 0, None)
                if handle == w.HANDLE(-1).value:
                    raise c.WinError(c.get_last_error())
                pp = c.c_void_p()
                keep = False
                try:
                    if not self.h.HidD_GetPreparsedData(handle, c.byref(pp)):
                        raise c.WinError(c.get_last_error())
                    caps = CAPS()
                    if self.h.HidP_GetCaps(pp, c.byref(caps)) != 0x110000:
                        continue
                    if (caps.UsagePage, caps.Usage, caps.FeatureReportByteLength) == (12, 1, 17):
                        handles.append(handle)
                        keep = True
                finally:
                    if pp:
                        self.h.HidD_FreePreparsedData(pp)
                    if not keep:
                        self.k.CloseHandle(handle)
            if not handles:
                raise DeviceNotFound('Patched M82 not found. Connect USB and install the compatible USB clock firmware.')
            if len(handles) != 1:
                raise DeviceNotFound('Multiple compatible devices found; connect only one M82 for synchronization.')
            return HIDDevice(self, handles.pop())
        finally:
            for handle in handles:
                self.k.CloseHandle(handle)

class HIDDevice:
    def __init__(self, api, handle):
        self.api, self.handle = api, handle
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.api.k.CloseHandle(self.handle)
    def get_feature(self):
        report = c.create_string_buffer(17)
        if not self.api.h.HidD_GetFeature(self.handle, report, 17):
            raise c.WinError(c.get_last_error())
        return report.raw
    def set_feature(self, data):
        if len(data) != 17:
            raise ValueError('Expected a 17-byte Feature Report')
        report = c.create_string_buffer(data, 17)
        if not self.api.h.HidD_SetFeature(self.handle, report, 17):
            raise c.WinError(c.get_last_error())
