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

1. **FIOS stall (current).** Threads (main + 2 media + scheduler) all run;
   mutexes work — they ping-pong on `lwm=0x02960D80` in microsecond
   critical sections forever. `PS3_SYSFSLOG=1` (new patch) proves **zero**
   `sys_fs` open/stat/mkdir calls: workers never reach file I/O.
   RPCS3 comparison shows what should happen next: mediathread stats +
   creates `/dev_hdd1/PSASBRCACHE`, opens `cache.idx/dat`, main creates 4
   more threads + `sys_rwlock`s, then opens `system/saveicon.png` and
   `global.psarc`. Spin sites: main blocks at `lr=0x009A1E28`
   (func `0x009A1DD4`, reentrant-mutex wrapper around `sys_lwmutex_lock`
   NID `0x1573dc3f`); workers block at `lr=0x004AC46C`
   (func `0x004AC438`, which compares two guest words `[r10+0x10]` vs
   `[r11+8]` and takes the "invalid cond" path when they match).
   Hypotheses, in order: (a) BE/LE flag misread in the FIOS cond struct
   (same class as the `CellSyncMutex` ticket-lock bug); (b) a silent HLE
   no-op during FIOS init leaves worker structs zeroed; (c) `sys_rwlock`
   recursion semantics differ. Next: watch the two compared guest words
   (PPU_WVAL) or trace which init write is missing vs RPCS3.
- 2026-09-25: `TTY_BT=invalid cond` captured both backtraces
  (`[CHAIN:tty-bt]`). Worker: `... 0099F004 004AB9BC 004ABA34 004ACADC
  0049F730 004ABFF4`. Scheduler: `... 0099F004 004AB9BC 004ABA34 004ABFF4`.
  Worker check (func `0x004ACADC`): `lwzu r0,0x10(r3)` — if the count word
  at cond+`0x10` is zero, calls print (`0x4ABA34`) with format from TOC and
  name from cond+`0x8` ("fios worker cond" / "scheduler.m_ioCond").
   Main spin is func `0x009A1DD4` (reentrant-mutex wrapper: lock via
   `sys_lwmutex_lock` NID `0x1573dc3f`, owner-tid in `+0x8`, count in `+0x0`).
   Mutexes themselves are healthy (microsecond critical sections, all tids
   progress); the guarded predicate never becomes true. `PS3_SYSFSLOG`
   (new diag) confirms zero `sys_fs` open/stat/mkdir — stall is purely sync,
   before any file I/O. RPCS3 divergence point: main should flow to
   `sys_rwlock_create` + `/dev_hdd1/PSASBRCACHE` setup + 4 more threads.
- 2026-09-25: `PS3_HLE_TRACE=N` (first-N-calls boot trace) decoded the
  steady loop: `sys_ppu_thread_get_id` (1368x) + `sys_lwmutex_lock` (764x) +
  `sys_lwmutex_unlock` (757x). Boot order: ~10 `sys_lwmutex_create`, one
  `sys_time_get_system_time`, then the two-site lock/unlock spin
  (`lr=0x009A1E28` in `0x009A1DD4` + `lr=0x009A219C` in helper `0x009A2180`
  which locks `object+448`). The `bl 0xB0D588` in the worker timeout path
  resolves to `sys_lwcond_wait` (NID `0x2a6d9d51`) — never reached, since
  workers take the count-zero branch first. `sys_ppu_thread_get_id`
  verified correct (real ctx thread ids). Callgraph built
  (25,544 funcs, 1M edges):   `0x009A1DD4` has 5 callers
  (`009951D4/E0`, `0099D7F4/40`, `009B6E74`); `0x004ACADC` has 8
  (`0049F730`, `004A3550`, ...). Open question remains who fills
  cond+`0x10` — the FIOS submit path from main never runs.
- 2026-09-25: widened `ppu_dump_guest_stack` code window `0x600000` ->
  `0x1000000` (was hiding all 9MB+ game frames). Full main stack shows a
  LIVE init loop, not a stuck thread:
  `00075A50 → 0048AB30 → 004865C4 → 009D4624 → 004ABEEC → 009A559C →
  00487898 → 009A3318 → ... → 0049930C → 0049D6C4 → 00499140 → 004A1800 →
  004ACADC → 004ABA34 → 004AB9BC → 0024F35C`. `PPU_WWATCH=02960D70`
  (main's FIOS object: `+0x0` count, `+0x8` owner) shows zero-init by
  `009A1ED0`, count-ups by `009A1DD4` (1,2,3) and count-downs by `009A1D90`
  (2,1,0) — the queue fills AND drains, cycling forever. Livelock, not
  deadlock. Added `RWLOCK create` log: main creates 7 rwlocks then never
  reaches RPCS3's next steps (2MB alloc, SPU event setup, thread batch 2,
  `PSASBRCACHE`, `global.psarc`). Down-counter `009A1D90` disassembled
  (17 instr: decrement count, `sys_lwmutex_unlock` only at zero) — healthy
  drain-to-zero signaling confirmed.
- 2026-09-25: lock/unlock audit (`PS3_HLE_TRACE=3000`): every lock paired
  with unlock on the SAME mutex (balanced). 10 mutexes up front
  (`0x02960C90-0x02960D30`, 40 bytes apart = slot-waiter `0099D7F4`'s
  `base+40*index+8` array) + heap ones. Steady loop alternates two sites
  across MANY mutexes = main polling an 8-slot worker barrier that never
  fills. Verdict: NOT a sync bug — livelock with no work submitted.
  Suspects: (a) silent HLE no-op in FIOS init (6x `sys_event_flag_clear`
  stubs at boot!); (b) lost cond/event wakeup — audit `sys_lwcond_signal`
  / `sys_event_flag_set` delivery next; (c) BE/LE-swapped readiness flag.
- 2026-09-25: signal audit done — both layers look correct in isolation
  (`sysPrxForUser` real CV impl is SHADOWED: `ppu_sysprx` registers ctx
  no-op `signal`/`wait` for all `sys_lwmutex_*`/`sys_lwcond_*`, dispatched
  first). But workers never reach `wait` (count-zero branch), so signals
  are moot. Decisive probe (temporary lift patch, since reverted):
  global `r10=0x00B11590`, `v1=[+0x10]=0` vs `v2=[+0x18]=2` — producer
  counter stuck at 0, consumers expect 2. `PPU_WWATCH`: scheduler area
  (`0x40032270`) fills correctly (names, pointers, mutexes); worker area
  (`0x40046F00`) gets ONLY memset zeros (`009A1B60`, confirmed memset by
  disasm) — fill skipped via untaken branch. 2-core affinity: still spins
  (not a startup race). `009A1B60` has 85 callers. Next: find the init
  caller that memsets-then-skips-fill; its branch likely reads a failed
  HLE result.
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
