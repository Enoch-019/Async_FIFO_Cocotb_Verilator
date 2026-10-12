# Asynchronous FIFO Verification with Cocotb and Verilator

A parameterized SystemVerilog asynchronous FIFO with a Python verification environment built using Cocotb and Verilator. The testbench checks data integrity, FIFO ordering, boundary behavior, pointer wraparound, and coordinated reset across independent read and write clocks.

The RTL originates from the ECE 593 asynchronous FIFO team project. This repository adapts its final RTL for Python-based verification and fixes its memory-depth and synchronizer-width parameterization.

## Project files

| File | Purpose |
| --- | --- |
| `design.sv` | FIFO top module, memory, pointer logic, and two-stage pointer synchronizers |
| `test_fifo.py` | Clock/reset generation, stimulus drivers, port monitors, deque scoreboard, and three tests |
| `run.py` | Command-line configuration, Verilator compilation, and Cocotb test execution |
| `.gitignore` | Excludes virtual environments, caches, build directories, and waveforms |

All three source files sit in the repository root. No UVM library is required.

## FIFO design

Writes and reads use separate clocks. Each domain maintains a binary pointer for memory addressing and a Gray-coded pointer for transfer to the other clock domain. Two-stage synchronizers transfer the Gray-coded pointers; local logic uses them to generate `wfull` and `rempty`.

| Parameter | Meaning | Default | Main tested configuration |
| --- | --- | --- | --- |
| `ASIZE` | Memory address width; depth is `2**ASIZE` | 4: 16 words | 9: 512 words |
| `DSIZE` | Bits per word | 8 | 64 |

The runner accepts `ASIZE >= 2` and `DSIZE >= 1`. Not every accepted parameter combination has been verified.

### Interface

| Port | Direction | Meaning |
| --- | --- | --- |
| `wclk`, `rclk` | Input | Independent write/read clocks |
| `wrst_n`, `rrst_n` | Input | Active-low resets for the respective domains |
| `winc` | Input | Write request |
| `rinc` | Input | Read request |
| `wdata` | Input | Write data, `DSIZE` bits |
| `rdata` | Output | Combinational read data, `DSIZE` bits |
| `wfull` | Output | Write-domain full flag |
| `rempty` | Output | Read-domain empty flag |

A write is accepted on a rising `wclk` edge when `wrst_n && winc && !wfull`. A read is accepted on a rising `rclk` edge when `rrst_n && rinc && !rempty`. The reset protocol used by this testbench disables traffic and resets both domains together.

`rdata` is an asynchronous, combinational memory output: `assign rdata = mem[raddr]`. An accepted read consumes the word present before the read edge advances the pointer. Data while empty is not treated as valid.

## Requirements

- Linux, including Ubuntu under WSL.
- Python compatible with Cocotb 2.1.0, including its matching shared library.
- GNU Make and a compatible C++ compiler.
- Verilator 5.036 or newer for Cocotb 2.x.
- Optional: GTKWave or another VCD viewer.

Validated locally with Cocotb 2.1.0 and the `verilator==5.48.0` Python distribution. That distribution's executable reports an unusual `vUNKNOWN` build label; the simulator identifies itself as Verilator 5.49 in the Cocotb log. A local Ubuntu/WSL run used Python 3.14.4 and GCC 15.2.

## Setup

Clone the repository and create a Python environment:

```bash
git clone https://github.com/Enoch-019/Async_FIFO_Cocotb_Verilator.git
cd Async_FIFO_Cocotb_Verilator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install cocotb==2.1.0 verilator==5.48.0
```

On Ubuntu, install compiler prerequisites if needed:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential
```

Put the Python-installed Verilator's native executable first on `PATH`:

```bash
export PATH="$(python -c 'import verilator; from pathlib import Path; print(Path(verilator.__file__).parent / "bin")'):$PATH"
verilator --version
```

This step matters if an older system Verilator is already installed. Repeat environment activation and the `PATH` command in a new terminal. If using a compatible system Verilator instead, install only Cocotb and omit the Python-package `PATH` command.

## Run

Run the default 16-word, 8-bit configuration:

```bash
python run.py
```

Run the 512-word, 64-bit configuration and record waveforms:

```bash
python run.py --asize 9 --dsize 64 --waves
```

Run a different reproducible random sequence:

```bash
python run.py --asize 9 --dsize 64 --waves --seed 123
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--asize` | 4 | FIFO address width |
| `--dsize` | 8 | FIFO data width |
| `--seed` | 42 | Seed used to initialize test randomization |
| `--waves` | Off | Enable VCD waveform recording |

A seed initializes the pseudorandom generator before stimulus is generated. With the same test code, configuration, tool environment, and random-call order, the same seed reproduces the same sequence. The DUT receives generated data and requests, not the seed.

## Verification environment

Drivers change inputs on falling clock edges and hold them through the following rising edge. Independent monitors capture inputs, flags, and read data during the low clock phase, then account for accepted transactions at the next rising edge.

The write monitor appends each accepted write to a Python `collections.deque`. The read monitor compares every accepted read against the oldest expected word and removes it from the queue. Blocked requests do not update the model. This checks ordering and data integrity without deriving expected data from DUT internals.

Sampling read data before the rising edge is essential for this combinational-read interface: sampling after the pointer updates can capture the next word instead of the consumed word.

Full and empty flags include pointer-synchronization latency. Tests allow flags to settle rather than requiring them to equal instantaneous global queue occupancy.

### Tests

| Test | Main checks |
| --- | --- |
| `boundaries_wrap_and_reset` | Empty read attempts, exact-capacity filling, blocked full writes, complete draining, three fill/drain cycles, reset with queued data, and fresh post-reset traffic |
| `random_concurrent_traffic` | Concurrent randomized enables/data with write faster than read, repeated pointer wraparound, final drain, and matching accepted write/read totals |
| `read_faster_than_write` | Concurrent traffic with clock rates reversed, empty-read pressure, data integrity, and matching accepted totals after draining |

The default write period is 1334 ps, approximately 749.625 MHz; the read period is 4000 ps, or 250 MHz. The write period approximates 750 MHz at 1 ps resolution. The third test reverses these rates.

Coordinated reset clears the expected queue. The directed test therefore intentionally permits different cumulative write/read totals: unread data is discarded by reset.

## Results and waveforms

The local 512x64 run with seed 42 reported:

```text
TESTS=3 PASS=3 FAIL=0 SKIP=0
```

Patched 16x8 and 512x64 configurations passed the three-test suite in development; 512x64 was also checked with seed 123. These results demonstrate the exercised scenarios, not exhaustive correctness or coverage closure.

Generated outputs include:

- `sim_9_64/`: generated C++ model and simulation executable for that configuration.
- `sim_9_64/results.xml`: machine-readable test results.
- `dump.vcd`: waveform recording when running from the project root with `--waves`.

Open the waveform with:

```bash
gtkwave dump.vcd
```

In GTKWave, select the `fifo` scope, append the desired signals, and zoom to a useful time interval. Start with clocks, resets, enables, data, full, and empty. Rerunning with `--waves` can overwrite `dump.vcd`; copy it first if you want to retain a particular run.

## RTL corrections

The final source from the original team project required these corrections:

1. Pass `ASIZE` to both pointer synchronizer instances. They previously retained their default address width when the top-level width changed.
2. Allocate memory as `mem[0:(1 << ADDRSIZE)-1]` instead of the hard-coded `mem[0:444]`, which provides only 445 entries.
3. Explicitly declare the previously implicit `rempty_val` and `wfull_val` signals.

The unmodified final RTL failed the three-test suite when configured as 512x64 during development. The patched version passed. This repository contains the patched RTL; the runner's historical source-selection lines remain as comments, and `--original` is no longer supported.

## Known limits

- Functional digital simulation does not model analog metastability or replace static CDC analysis and timing constraints.
- No functional/code coverage collection or coverage-closure claim is included.
- Tests reset both domains together; independent one-domain resets are not verified.
- Clock stoppage, arbitrary clock-phase sweeps, and coincident rising-edge cases are not targeted.
- Internal Gray-pointer transitions and synchronizer topology do not have dedicated assertions here.
- The current pointer-increment expressions produce Verilator `WIDTHEXPAND` warnings. The runner uses `-Wno-fatal` so warnings do not stop the build; explicit width cleanup remains future work.

## Author and provenance

Maintained by [Enoch-019](https://github.com/Enoch-019). The FIFO RTL derives from the ECE 593 team project; the Cocotb environment and runner were developed with AI assistance and exercised locally using Verilator.
