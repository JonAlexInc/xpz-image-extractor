# Third-party notices

The MIT license in this repository applies to the new application code. It does not relicense dependencies or their native components.

The initial Windows executable bundles these components:

| Component | Notice |
| --- | --- |
| Python 3.12.14 | [Python license and notices](third_party_licenses/Python.txt) |
| Tcl/Tk 8.6 | [Tcl terms](third_party_licenses/Tcl.txt), [Tk terms](third_party_licenses/Tk.txt) |
| Pillow 12.3.0 and its bundled native dependencies | [Pillow license and dependency notices](third_party_licenses/Pillow.txt) |
| PyInstaller 6.22.3 bootloader and runtime components | [PyInstaller terms, including the bootloader exception](third_party_licenses/pyinstaller.txt) |

Retain these notices when redistributing the executable. Builds using different runtime or dependency versions should carry the notices supplied with those versions. Development-only packages are not intentionally bundled as application dependencies.

Source references consulted during investigation are listed separately in [DEVELOPMENT.md](DEVELOPMENT.md).
