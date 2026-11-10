# Third-party components

Dependencies are Git submodules, pinned to the versions used for validation. They are not required for ordinary HID synchronization.

| Dependency | Purpose | Pinned commit |
|---|---|---|
| [kagaimiq/jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool) | BR25 protocol, RAM loader, Windows SCSI definitions | `adb3f18889e88ac512ce0a3c4d8cc3d3cb30696a` |
| [kagaimiq/jl-misctools](https://github.com/kagaimiq/jl-misctools) | JLFS unpacking, CRC, SFC cipher | `0a5b12db0ef38f3042acffbe2452730a37fd2405` |
| [jvitkauskas/pi32v2-isa](https://github.com/jvitkauskas/pi32v2-isa) | PI32v2 assembler, linker, simulator | `8f58bb5f4c6e10d318bb8501f85e9eb5fdeaaccc` |

See each dependency's license files. The PI32v2 project distinguishes code and documentation/table licenses. Its simulation evidence primarily targets an AC791N board; the M82 BR25 hardware results listed in this repository provide the separate device-specific check.

The published SDK copy [qqq5127/AC6966B](https://github.com/qqq5127/AC6966B) was consulted to interpret functions and structures during research. It is not included, is not MIVO's source tree, and is not needed to use or rebuild this patch.

The sector bundle necessarily includes modified portions of the original device firmware and its resources. Those portions remain subject to their owners' rights; this project's MIT license does not relicense them. No ownership or manufacturer endorsement is claimed.
