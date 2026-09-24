# allstars-ps3

Native PC port of **PlayStation All-Stars Battle Royale (BCUS98472)** via
[ps3recomp](https://github.com/sp00nznet/ps3recomp) static recompilation.
PPU is lifted to C and linked against the ps3recomp runtime (D3D12 backend on
Windows). No emulator required.

> **Legal:** you must own the BCUS98472 disc and dump it plus its `.dkey`
> yourself. This repo contains no Sony code, keys, firmware, game binaries,
> or assets — only the port project, scripts, and runtime patches.

## Status

- Decrypted `EBOOT.BIN` -> `EBOOT.BIN.elf` (13.2 MB, PPC64) with own `.dkey`
- Analysis: 25 modules / 376 imports, 24,530 PPU functions, 3 SPU images
- Lift: 25,544 PPU functions (with `--hle-stubs`) + 1098 HLE handlers,
  2095 SPU functions across 3 images
- Builds: `MyGameRecomp.exe` (~170 MB) with clang-cl 23 + MSVC
- Boots: CRT -> SPURS "Main"+"SCREAM" -> `cellGame BootCheck (BCUS98472)` ->
  FIOS 1.3.5 -> D3D12 init -> stalls on `fios worker cond` (invalid lwcond)
- Zero `unresolved NID` at boot (8 fixed: 7x cellSpursJq + _sys_spu_printf)

See [docs/STATUS.md](docs/STATUS.md) for the detailed boot log and blockers.

## Layout

```
allstars-ps3/
  CMakeLists.txt   # port build (based on ps3recomp templates/project)
  main.cpp         # runner + PARAM.SFO title-id init fix
  stubs.cpp        # game-specific overrides (currently empty)
  config.toml      # recompiler/module settings reference
  tools/
    decrypt_iso.py # Redump ISO -> decrypted ISO with own .dkey (AES-CBC, IV=LBA)
  patches/
    ps3recomp-runtime-allstars.patch  # 8 missing HLE handlers (JQ attrs, spu printf)
  docs/
    STATUS.md      # current boot status + next steps
```

## Build

Prerequisites: Python 3.10+, CMake 3.20+, Ninja, VS 2022, LLVM (clang-cl).

```bat
:: 1. ps3recomp checkout + our runtime patch
git clone https://github.com/sp00nznet/ps3recomp.git
cd ps3recomp
git checkout 39e4f49286447b3ae3dcc2358700c840860ee677
git apply ..\allstars-ps3\patches\ps3recomp-runtime-allstars.patch

:: 2. lift (needs decrypted EBOOT.BIN.elf from your own dump)
set PYTHONUTF8=1
python tools\ppu_loader.py EBOOT.BIN.elf -o loader_out
python tools\ppu_lifter.py EBOOT.BIN.elf ^
  --functions loader_out\EBOOT.BIN.functions.json ^
  --hle-stubs loader_out\EBOOT.BIN.imports.json ^
  -o ..\allstars-ps3-work\recompiled
python tools\gen_hle_nids.py --all ^
  --out ..\allstars-ps3-work\recompiled\ppu_hle_nids.cpp

:: 3. configure + build (VS prompt for headers, LLVM for compiler)
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
set PATH=C:\Program Files\LLVM\bin;C:\Program Files\CMake\bin;%PATH%
cmake -B build -G Ninja -DCMAKE_C_COMPILER=clang-cl ^
  -DCMAKE_CXX_COMPILER=clang-cl ^
  -DPS3RECOMP_DIR=<ps3recomp> -DRECOMP_DIR=<recompiled> <allstars-ps3>
cmake --build build
```

Run (needs decrypted game files for VFS):

```bat
set PS3_VFS_ROOT=C:\path\to\vfs
build\MyGameRecomp.exe C:\path\to\EBOOT.BIN.elf
```

`tools/decrypt_iso.py` decrypts a Redump ISO with the `.dkey` sitting next
to it (same basename). It parses the region table (even regions plain, odd
encrypted) and AES-CBC decrypts per sector with IV = 12 zero bytes + BE LBA.

## Upstreaming

`patches/ps3recomp-runtime-allstars.patch` should go upstream to sp00nznet/ps3recomp:
the 7 `cellSpursJobQueueAttribute*` setters and `_sys_spu_printf_initialize`
are generic, not title-specific. The `main.cpp` PARAM.SFO init is already
upstream behavior in newer templates.
