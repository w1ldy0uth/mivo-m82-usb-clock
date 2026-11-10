# MIVO M82 USB Clock

[Русский](README.md) | [English](README.en.md)

Synchronize the **MIVO M82** speaker's clock with Windows local time over USB.

This project includes modified firmware distributed as a sector bundle, the PI32v2 source for the USB modification, a Windows synchronization utility, automatic synchronization at sign-in, and backup/restore tools.

Real USB SET/GET, the correct time on the display, and working audio have been confirmed on one speaker. The Windows audio driver is unchanged, and the original 16 multimedia buttons are preserved in the HID descriptor.

## Compatibility

**The M82 model name alone does not establish compatibility.** The tested platform is JieLi BR25 / AC696x, with 512 KiB SPI NOR flash, flash ID `CD7013`, SFC key `077A`, and an `AC696N_V160` SDK base. Only the exact firmware revision identified in [manifest.json](firmware/manifest.json) is supported.

The installer checks the hash of the entire static region against the known original or already-patched version. If it does not match, installation stops before erasing flash. There is no `--force` option. Other hardware revisions and SFC keys have not been tested.

## Quick start — firmware already installed

You need Windows and Python 3.11 or newer. Normal synchronization uses only the Python standard library and the Windows HID API.

```powershell
git clone --recurse-submodules https://github.com/w1ldy0uth/mivo-m82-usb-clock.git
cd mivo-m82-usb-clock
py -3 -m mivo_m82 read
py -3 -m mivo_m82 sync
```

`sync` sets the speaker to the **local date and time reported by Windows**, then reads the RTC back. Success is reported only after verification, with a maximum allowed difference of 2 seconds. The observed difference on the tested speaker was approximately 0.5 seconds.

If your Python installation does not provide the `py` command, replace `py -3` with the path to `python.exe`.

## Installing the firmware

Follow the [step-by-step installation guide](docs/INSTALL.md): make a backup, check compatibility, and then program the modified sectors. Flash operations require administrator privileges and additional dependencies. Normal clock synchronization does not require administrator privileges.

The firmware is distributed as [53,248 bytes of modified sectors](firmware/mivo-m82-usb-clock-v1.0.0.sectors.bin), rather than a full device dump. The tool preserves boot data and the current settings/pairing region. This `.bin` is **not a manufacturer update package**: do not copy it onto a USB drive as an update file or write it directly at address zero.

The detailed guides linked from this README are currently in Russian. Their command examples use the same tools and options documented here.

## Automatic synchronization

Run this command from the repository root:

```powershell
py -3 -m mivo_m82 install-autostart
```

A copy of the utility is installed in `%LOCALAPPDATA%\MivoM82Clock`, and a `MIVO_M82_Clock` entry is added to the current user's Windows startup configuration. At sign-in, it starts without a console window, waits 10 seconds, and then tries to find the speaker over USB for up to approximately three minutes. The process exits after the first verified synchronization. If you connect the speaker later, run `sync` manually.

The utility is copied out of the checkout, but the selected Python installation must remain available. Startup uses its `pythonw.exe`. The log is stored at `%LOCALAPPDATA%\MivoM82Clock\autostart.log`.

To disable automatic synchronization:

```powershell
py -3 -m mivo_m82 uninstall-autostart
```

Disabling startup does not modify the firmware. No persistent service, cloud automation, or periodic background polling is installed.

## Recovery and development

- [Restore the original firmware](docs/RECOVERY.md).
- [USB protocol and firmware architecture](docs/ARCHITECTURE.md).
- [Validation and limitations](docs/VALIDATION.md).
- [Rebuild from your own original dump](docs/BUILD.md).

Full original dumps, Bluetooth pairing data, and user settings are not included in this repository. The `backups/` and `build/` directories, along with logs, are excluded from Git.

Compatibility has been demonstrated on one hardware revision. Recovery through a hardware bootloader adapter and clock retention after a complete power loss have not been tested separately; see the validation and recovery guides before flashing another device.

## Licenses

Our original code is licensed under [MIT](LICENSE). The sector bundle contains modified portions of the manufacturer's original firmware; the MIT license does not cover third-party code or audio resources within it. Dependencies retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
