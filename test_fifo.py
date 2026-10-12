"""Black-box checks for this project's asynchronous, combinational-read FIFO.

Inputs are driven on falling edges. Monitors snapshot inputs/data while the
clock is low, then commit accepted transactions at the following rising edge.
This avoids accidentally checking the NEXT word after raddr advances.
"""
import os
import random
from collections import deque
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, ReadOnly, with_timeout


class Bench:
    def __init__(self, d):
        self.d = d
        self.depth = int(os.environ['FIFO_DEPTH'])
        self.mask = (1 << len(d.wdata)) - 1
        self.expected = deque()
        self.writes = self.reads = 0
        self.blocked_writes = self.blocked_reads = 0

    async def start(self, wp=1334, rp=4000):
        d = self.d
        d.wclk.value = d.rclk.value = 0
        d.winc.value = d.rinc.value = d.wdata.value = 0
        d.wrst_n.value = d.rrst_n.value = 0
        cocotb.start_soon(Clock(d.wclk, wp, unit='ps').start(start_high=False))
        cocotb.start_soon(Clock(d.rclk, rp, unit='ps').start(start_high=False))
        cocotb.start_soon(self.monitor_write())
        cocotb.start_soon(self.monitor_read())
        await self.reset()

    async def reset(self):
        d = self.d
        d.winc.value = d.rinc.value = 0
        d.wrst_n.value = d.rrst_n.value = 0
        self.expected.clear()
        await Timer(20, unit='ns')
        await ReadOnly()
        assert int(d.rempty.value) == 1 and int(d.wfull.value) == 0
        await FallingEdge(d.wclk)
        d.wrst_n.value = 1
        await FallingEdge(d.rclk)
        d.rrst_n.value = 1
        await Timer(20, unit='ns')

    async def monitor_write(self):
        d = self.d
        while True:
            await FallingEdge(d.wclk)
            await Timer(1, unit='ps')
            active = int(d.wrst_n.value)
            inc, full, data = int(d.winc.value), int(d.wfull.value), int(d.wdata.value)
            await RisingEdge(d.wclk)
            if active and int(d.wrst_n.value) and inc:
                if full:
                    self.blocked_writes += 1
                else:
                    assert len(self.expected) < self.depth, 'Accepted write beyond capacity'
                    self.expected.append(data)
                    self.writes += 1

    async def monitor_read(self):
        d = self.d
        while True:
            await FallingEdge(d.rclk)
            await Timer(1, unit='ps')
            active = int(d.rrst_n.value)
            inc, empty, data = int(d.rinc.value), int(d.rempty.value), int(d.rdata.value)
            await RisingEdge(d.rclk)
            if active and int(d.rrst_n.value) and inc:
                if empty:
                    self.blocked_reads += 1
                else:
                    assert self.expected, 'Accepted read with no expected data'
                    expected = self.expected.popleft()
                    assert data == expected, f'Read {self.reads}: got {data:#x}, expected {expected:#x}'
                    self.reads += 1

    async def write_cycles(self, n, probability=1.0):
        d = self.d
        for _ in range(n):
            await FallingEdge(d.wclk)
            d.winc.value = int(random.random() < probability)
            d.wdata.value = random.getrandbits(len(d.wdata))
            await RisingEdge(d.wclk)
        await FallingEdge(d.wclk)
        d.winc.value = 0

    async def read_cycles(self, n, probability=1.0):
        d = self.d
        for _ in range(n):
            await FallingEdge(d.rclk)
            d.rinc.value = int(random.random() < probability)
            await RisingEdge(d.rclk)
        await FallingEdge(d.rclk)
        d.rinc.value = 0

    async def drain(self):
        await self.read_cycles(self.depth + 12)
        await Timer(30, unit='ns')
        assert not self.expected, f'{len(self.expected)} words not drained'
        assert int(self.d.rempty.value) == 1
        assert int(self.d.wfull.value) == 0


@cocotb.test()
async def boundaries_wrap_and_reset(d):
    b = Bench(d)
    await b.start()
    await b.read_cycles(8)
    assert b.reads == 0 and b.blocked_reads >= 8
    for _ in range(3):
        before = b.writes
        await b.write_cycles(b.depth + 8)
        assert b.writes - before == b.depth
        assert int(d.wfull.value) == 1
        await Timer(20, unit='ns')
        assert int(d.rempty.value) == 0
        await b.drain()
    assert b.blocked_writes > 0
    await b.write_cycles(b.depth // 2)
    assert b.expected
    await b.reset()  # Coordinated reset discards queued data.
    await b.write_cycles(5)
    await b.drain()
    d._log.info('Directed: %d accepted writes, %d checked reads', b.writes, b.reads)


@cocotb.test()
async def random_concurrent_traffic(d):
    b = Bench(d)
    await b.start()
    w = cocotb.start_soon(b.write_cycles(b.depth * 20, 0.8))
    r = cocotb.start_soon(b.read_cycles(b.depth * 9, 0.7))
    await with_timeout(w, 1, 'ms')
    await with_timeout(r, 1, 'ms')
    await b.drain()
    assert b.reads > b.depth * 2, 'Insufficient pointer-wrap traffic'
    assert b.writes == b.reads
    d._log.info('Random: %d transactions checked', b.reads)


@cocotb.test()
async def read_faster_than_write(d):
    b = Bench(d)
    await b.start(wp=4000, rp=1334)
    w = cocotb.start_soon(b.write_cycles(b.depth * 6, 0.6))
    r = cocotb.start_soon(b.read_cycles(b.depth * 20, 0.9))
    await with_timeout(w, 1, 'ms')
    await with_timeout(r, 1, 'ms')
    await b.drain()
    assert b.writes == b.reads and b.reads > b.depth
    assert b.blocked_reads > 0
