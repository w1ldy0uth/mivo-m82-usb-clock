"""Per-user Windows startup, isolated from the checkout; no scheduled service."""
from datetime import datetime
from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import sys
import time

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'MIVO_M82_Clock'

def install_dir():
    if os.name != 'nt':
        raise OSError('Windows is required')
    return Path(os.environ['LOCALAPPDATA']) / 'MivoM82Clock'

def install():
    import winreg
    root = install_dir()
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise OSError('pythonw.exe is missing next to this Python interpreter')
    package = Path(__file__).resolve().parent
    target = root / 'mivo_m82'
    root.mkdir(parents=True, exist_ok=True)
    if package != target.resolve():
        shutil.copytree(package, target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    launcher = root / 'launch_clock.py'
    prefix = ('from pathlib import Path\nimport sys\n'
              'sys.path.insert(0, str(Path(__file__).resolve().parent))\n')
    launcher.write_text(prefix + 'from mivo_m82.autostart import run\nrun()\n', encoding='utf-8')
    (root / 'sync_once.py').write_text(prefix +
        'from mivo_m82.__main__ import main\nraise SystemExit(main())\n', encoding='utf-8')
    command = subprocess.list2cmdline([str(pythonw), str(launcher)])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    return {'installed_to': str(root), 'run_value': VALUE_NAME, 'command': command,
            'note': 'Keep the selected Python installation; the repository checkout can be moved.'}

def uninstall():
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        try:
            winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
    return {'autostart': 'disabled', 'note': 'Firmware and manual synchronization are unchanged.'}

def run():
    root = install_dir()
    root.mkdir(parents=True, exist_ok=True)
    logfile = root / 'autostart.log'
    def log(message):
        if logfile.exists() and logfile.stat().st_size > 131072:
            logfile.write_text(logfile.read_text(encoding='utf-8')[-65536:], encoding='utf-8')
        with logfile.open('a', encoding='utf-8') as stream:
            stream.write(datetime.now().isoformat(' ', timespec='seconds') + ' ' + message + '\n')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, r'Local\MivoM82ClockStartup')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if ctypes.get_last_error() == 183:
            return
        log('Started; waiting for M82 USB')
        time.sleep(10)
        deadline = time.monotonic() + 180
        last_error = ''
        while time.monotonic() < deadline:
            try:
                python = Path(sys.executable).with_name('python.exe')
                result = subprocess.run([str(python), str(root / 'sync_once.py'), 'sync'],
                    cwd=root, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=12, creationflags=0x08000000)
                if result.returncode == 0:
                    log('SUCCESS: ' + result.stdout.strip().replace('\n', ' | '))
                    return
                last_error = ' '.join((result.stderr or result.stdout).strip().splitlines()[-1:])
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
            time.sleep(5)
        log('Stopped after timeout: ' + last_error)
    finally:
        kernel.CloseHandle(mutex)
