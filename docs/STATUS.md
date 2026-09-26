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
- 2026-09-25: root-caused to the worker-count field. Worker check
  (`004ACADC`) compares `[global+0x10]` vs `[arg+0x18]`; global is BSS
  `0x00B11590` (pointer installed statically via `[TOC+0x6B0]`, never
  written at runtime). Lifted-code probe: `v1=0` vs `v2=2` always.
  `PPU_WWATCH` proves scheduler struct (`0x40032270`) fills correctly
  (names incl. byte-built "fios scheduler 1", pointers, mutexes) while
  worker area gets only memset zeros — the worker-init loops in FIOS init
  (`0x49EB78`: `for i < [r31+0x178]: cond_init(..., 'fios worker cond')`)
  are SKIPPED because count `[r31+0x178]` stays 0
  (`PPU_WWATCH=400323E8`: zeroed, never set). Name pointers traced to TOC
  slots (`0xC84AFC`/`0xC84B10`); fill sites `0x49E6C0` (scheduler, runs) vs
  `0x49EB68` (workers, skipped). Next: find what computes `[r31+0x178]`
  (worker count) — likely gated on an HLE/syscall result during FIOS init.
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
  (not a startup race). `009A1B60` has 85 callers.
- 2026-09-25: per-tid check values — ALL threads poll the SAME global
  (`r10=0x00B11590`, `v1=0`, `v2=2`): main (3 objects), media (shared
  `0x40032358`), scheduler (`0x400322B0/08`). Scheduler-init `0049E5B0`
  (sole caller `0049EE74`) gates on a VIRTUAL call (`bctrl 0x49EFD4`):
  nonzero → init, zero → skip. `0049E5B0` body is straight-line with
  returning `bl`s, yet its count/field stores never land — implicating its
  input config (`r5`/`r26` chain). `004ABEEC` (cond-init helper) has 11
  callers; `0049E6B0`-region is mid-function (straight-line fall-through
  from `0x49E640+`), not a separate entry. Next: capture the virtual-call
  result at `0049EE74+0x49EFD4` and the `r5` config value (probe the
  `bctrl` target or WVAL the config struct).
- 2026-09-26: removed dead pre-seed hack #2 (`*(0x400323E8)=1` in
  `main.cpp`, predates investigation): it wrote heap VM before ELF load,
  wiped by init memset — proven inert, was masking nothing. Gate test
  (`PPU_THREADGATE=1` + release-on-main-block): workers suspend (zero
  worker prints) but main spins `opWait` alone — no batch 2, no sys_fs.
  Gate holds workers but nothing releases them usefully. RPCS3 oracle
  rebooted (BCUS98472, past FIOS init) to compare menu-reaching behavior.
- 2026-09-26: race theory DEAD — timestamp-ordered log proof: first
  invalid print (line 144) is main; worker-struct fills land lines
  192-233 (names incl. "fios mediathread 2/3", pointers, mutexes, counts);
  threads start 238+. Order is CORRECT (fill before start). Uncapped watch
  confirms full init. New model: TWO check sites — `004ACADC`
  (`[arg+0x10]==0` → print, fires on genuinely-empty per-worker slots)
  and `004AC430` (global vs expect → lock path, silent). Everyone idles
  correctly; the FIRST OP (kick) never arrives because game main sits in
  the FIOS pump waiting for completions of ops it never submitted. Next:
  back up main's stack past the pump into game code (`00075A50` region)
  to find the submission trigger — or check game-level gates (NP/Sail/
  Trophy/Save) via long-window module-NID sampling.
- 2026-09-26: init bisected to a ~20-instruction window — execution provably
  reaches the `0x4AC820` cond-init calls (their name/magic writes land) but
  never the `+0x1BC` stores two calls later, implicating the `0x4ABEEC`
  call at `0x49E710` (its `sys_lwmutex_create` check gates print-vs-return;
  our create always succeeds). `LWM_COUNT` shows 24 clean creates, no
  duplicates. METHOD CORRECTION: `PPU_WWATCH` print cap (default 64)
  makes post-cap silence look like "never written" — re-ran the global
  watch with `PPU_WWATCH_MAX=0` (unlimited): still ZERO writes in 30s,
  so the producer-counter conclusion stands on solid ground. Read-probes
  (`CONDCHECK`) remain the source of truth for values; write-watches need
  uncapped reruns before concluding absence.
- 2026-09-26: pre-fill experiment (NEGATIVE result): seeded BSS global
  counter `*(0x00B115A0)=2` in `main.cpp` before `ppu_run` — boot
  UNCHANGED (336k invalid-cond prints, no batch 2, no sys_fs). Proves the
  global is NOT the (only) gate: worker check `004ACADC`
  (`[arg+0x10]==0` → print) is independent of the global check
  (`004AC438`), and worker structs stay empty regardless. Reverted.
  Reframed: TWO empty structs (BSS global + per-worker args), both
  memset-only. Suspect BSS-vs-heap object mismatch — init fills one
  instance, threads poll another (unpublished global link?). Next: map
  which object each thread's arg chain resolves to and find the linking
  pointer that should unify them.
- 2026-09-25: `PS3_SCTRACE` syscall census (210 calls, ALL tid=1): mutex
  create/lock/unlock balanced, 7x `SYS_RWLOCK_CREATE` (from `004AC944`
  via `004A7C00`), 3x `SYS_MEMORY_ALLOCATE`, SPU init, event setup — then
  main goes HLE-only forever. 70s `HLE_BT_EVERY` sampling: max tid 5 (no
  batch 2), only 4 NIDs ever. Worker object (`0x40032358`) DOES get filled
  (`FIOS`, name ptr, `mutex`, values 1/2/3) — but the `2/3/1` writes come
  from HOST side (bogus `0x20002F00` attribution = HLE, likely
  `sleep_queue` slot ids from mutex creation, not FIOS payload!). The
  "expect=2" is probably a mutex slot id, reframing the check again.
  Prints (`228k` in 30s) must fire at equal-valued sites. Next: identify
  the host-side writer of `2/3/1` (match create-call order to slot ids)
  and pin down the print site's Cell values.
- 2026-09-25: allocator EXONERATED — lifted probe shows the virtual alloc
  at `0049EE74+0x49EFD4` returns heap object `0x400321D0` (nonzero, once),
  so `0049E5B0` init is entered with a valid object. Grep over the lift
  for writers of `[global+0x10]`: only `004ABE38`/`004AC810` match the
  read+write pattern, but both write `[r31+0x10]` (object field), merely
  READING the global — no code writes the producer counter, and the
  pointer slot (`[TOC+0x6B0]` = `0xC84E18`) is never swung either. The
  submit path is absent from the executed code, not just skipped: main
  never reaches op submission because it   never leaves the barrier poll,
  and the barrier needs a submission to release. Circular stall rooted
  one level up — what main waits on BEFORE its first submit (likely the
  SPU/taskset readiness or the 2MB-alloc/event setup RPCS3 shows next).
- 2026-09-26: cap-trap CONFIRMED biting: uncapped re-watch proves worker
  structs ARE filled (names incl. "fios mediathread 2", pointers, mutexes
  — 30 nonzero of 130). Init runs; workers are set up; "invalid cond"
  prints are verbose-idle logging, not errors. Everyone idles correctly
  with no work: game waits in FIOS pump, pump waits for game ops. The
  first-op trigger is missing. LEAD: `PPU_THREADGATE` exists for exactly
  this startup race (suspend workers till creator blocks) but releases
  only on event-queue waits — our main only mutex-blocks, so it would
  deadlock differently. Next: extend the gate to release on first
  lwmutex-block (5-line change), letting main finish linking before
  workers run.
- 2026-09-25: thread-startup handshake HEALTHY; op-waiter `00497F08`
  decoded (calls check `004AC430(obj+16)`, returns `[obj+0x44]`, main loops
  on it). Dual-gate file-I/O test (`PS3_FSLOG=1` + `PS3_SYSFSLOG=1`):
  ZERO opens/stats through all three layers — stall 100% pre-I/O,
  airtight (`HLETRACE` covers every NID incl. ctx handlers; syscalls gated
  separately). Remaining: the op-submission trigger main never reaches.
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
