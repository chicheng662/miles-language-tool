# Third-party software and licensing scope

The PolyForm Noncommercial license applies to original Miles Language Tool source and application code only. It does not relicense fonts, external tools, runtimes, or libraries. Rights granted by their own licenses remain unchanged.

| Component | License | Source / build reference |
| --- | --- | --- |
| JPEXS Free Flash Decompiler 26.3.0, invoked as a separate executable process | GPL-3.0-or-later | https://github.com/jindrapetrik/jpexs-decompiler/releases/tag/version26.3.0 |
| FFDec library, dynamically used by the Java font helper | LGPL-3.0-or-later | https://github.com/jindrapetrik/jpexs-decompiler/tree/version26.3.0/libsrc/ffdec_lib |
| Eclipse Temurin OpenJDK JRE 17.0.20.1+1 | GPL-2.0 with Classpath Exception and bundled notices | https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20.1%2B1 ; corresponding source: https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk-sources_17.0.20.1_1.tar.gz |
| Noto Sans, Noto Sans KR and Noto Sans SC | SIL OFL 1.1 | `fonts/OFL*.txt`, `fonts/DERIVATION.md`, https://github.com/google/fonts |
| Python / Tcl / Tk | PSF / Tcl/Tk licenses | https://www.python.org/ ; https://www.tcl.tk/ ; Tcl 8.6.15 text: `licenses/TCL-8.6.15-license.terms`; other full licenses in the portable package |
| PyInstaller | GPL with bootloader distribution exception | `licenses/PYINSTALLER-COPYING.txt`; https://github.com/pyinstaller/pyinstaller/blob/v6.22.0/COPYING.txt |

Full GPL and LGPL texts are in `licenses/`; portable distributions also preserve the original runtime licenses and notices. JPEXS and FFDec corresponding source for the bundled version is available at the exact release above, including https://github.com/jindrapetrik/jpexs-decompiler/archive/refs/tags/version26.3.0.zip . Preserve source access directions when redistributing.

The Java helper uses the externally replaceable FFDec library at run time. See BUILDING.md for recompilation and library replacement instructions. The project's noncommercial terms do not restrict modification or debugging rights in third-party libraries granted by their respective licenses.

Asset format documentation was consulted in https://github.com/Tkachov/Overstrike . The Python readers are an independent implementation; no Overstrike binary is bundled.

Game executables, original GFX, localization tables, generated subtitle packages and player saves are not distributed here. All related game and trademark rights belong to their respective owners.
