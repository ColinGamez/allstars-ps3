# Status — All-Stars (BCUS98472)

Updated: 2026-09-24. Exe: `MyGameRecomp.exe` ~170 MB (PPU + 3 SPU images).

## Boot sequence (working)

```
=== ps3recomp game runner ===
[ppu] PT_TLS template, 2 PT_LOAD segments, entry OPD 0x00C5B490
[cellGame] title id from PARAM.SFO ('.../vfs/PS3_GAME/PARAM.SFO'): 'BCUS98472'
[sys_memory] allocate 0x100000, 0x2C00000, 0x2A00000
[SPU] initialize(nspu=6)
cellSysmodule: SPURS, RTC, SYSUTIL_NP, USERINFO, PAMF, SAIL, HTTP, HTTP_UTIL,
  HTTPS, NET, SYSUTIL_GAME, IO, FS
[cellSpurs] AttributeInitialize + Initialize "Main" + "SCREAM" (2 SPUs each)
[cellSpurs] CreateTaskset x4
[cellSpursJq] CreateJobQueue()
[cellGame] BootCheck: type=1, titleId='BCUS98472'
[D3D12] Debug layer enabled
FIOS 1.3.5 initialized + fios mediathread/scheduler threads
STALL: `wait for invalid cond 'fios worker cond'` / `'opWait'` loop
```

Zero `unresolved NID` (was 8 on first HLE-stub-less lift).

## Analysis numbers

- ELF: `EBOOT.BIN.elf` 13,235,512 bytes, ELF64 BE PPC64, entry `0xC5B490`
- Imports: 25 modules, 376 funcs (cellSpurs 39, SpursJq 14, GcmSys 28,
  Sail 36, Pamf 4, sceNp 53, Voice 15, Http 14, ...)
- NID DB: 133/376 unresolved names (runtime covers the modules; DB gaps)
- PPU functions: 24,530 found -> 25,544 lifted (with `--hle-stubs`)
- SPU: 3 images, 280 KB total -> img0 266f, img1 1146f, img2 683f
  (img2: 378 `.word` unsupported — data-in-code or new ops)

## Blockers (in order)

1. **FIOS stall (current).** `PS3_FSLOG=1` shows zero file opens — dies in
   thread sync first. `sys_lwcond` exists but FIOS worker conds report
   "invalid", suggesting static BSS cond/mutex init isn't recognized.
   Compare RPCS3 FIOS flow after scheduler creation; inspect the guest
   cond object address (static vs dynamically created).
2. **SPU workload registration.** Images compile/link (symbol-prefixed)
   but no `spu_workloads.c` yet — `cellSpurs` dispatches by fingerprint,
   so jobs will miss until `build_spu_workloads.py` output is added.
3. **Online stack.** sceNp/Voice/Http/Trophy will need offline
   NOT_CONNECTED behavior to get past menus once boot proceeds.
4. **Movies.** cellSail completes immediately (no playback); cinematics
   may need skipping logic.

## Repro

```
set PS3_VFS_ROOT=<work>\vfs   (contains decrypted PS3_GAME/)
build\MyGameRecomp.exe <work>\EBOOT.BIN.elf
```

First boot without `--hle-stubs` dies at `0x39800000` (`li r12,0` import
trampoline) — expected; re-lift with `--hle-stubs` per GETTING_STARTED.
