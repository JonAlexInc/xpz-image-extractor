# Development references

The interface and extraction implementation were written for this project with assistance from OpenAI Codex. No functions or code blocks were copied from XboxToolkit or XPRXpress. The investigation was not a clean-room process: existing source and format definitions were consulted.

- [XboxToolkit](https://github.com/Team-Resurgent/XboxToolkit): its XPR conversion source was read during the initial investigation.
- [XPRXpress](https://github.com/UkooLabs/XPRXpress): project metadata and documentation were inspected for Windows compatibility.
- [Cxbx-Reloaded Xbox format definitions](https://github.com/Cxbx-Reloaded/Cxbx-Reloaded/blob/master/src/core/hle/D3D8/XbD3D8Types.h): consulted to verify Xbox pixel-format numeric identifiers.

The supplied sample was inspected to determine its XPR1 resource table, offsets relative to byte 12, zlib compression, resource boundaries, and tightly packed pixel rows. Its original bytes and exported assets are not included in the repository or release.

Neither XboxToolkit nor XPRXpress is a dependency or part of the distributed executable. This document records development provenance; it does not replace the licenses of components that are actually bundled.
