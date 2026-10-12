import argparse
import os
from pathlib import Path
from cocotb_tools.runner import get_runner

p = argparse.ArgumentParser()
p.add_argument('--asize', type=int, default=4)
p.add_argument('--dsize', type=int, default=8)
# Old option: selected between original and patched RTL files.
# p.add_argument('--original', action='store_true')
# Removed because this folder contains only design.sv.
p.add_argument('--seed', type=int, default=42)
p.add_argument('--waves', action='store_true')
a = p.parse_args()
if a.asize < 2 or a.dsize < 1:
    p.error('ASIZE must be >= 2; DSIZE must be >= 1')
root = Path(__file__).resolve().parent
os.environ['FIFO_DEPTH'] = str(1 << a.asize)
runner = get_runner('verilator')
# Old build directory selection:
# build = root / ('sim_original' if a.original else f'sim_{a.asize}_{a.dsize}')
build = root / f'sim_{a.asize}_{a.dsize}'
# Old source selection (RTL files were inside an rtl folder):
# runner.build(sources=[root / 'rtl' / ('original_design.sv' if a.original else 'design.sv')],
# design.sv now sits beside run.py and test_fifo.py.
runner.build(sources=[root / 'design.sv'],
             hdl_toplevel='fifo', parameters={'ASIZE': a.asize, 'DSIZE': a.dsize},
             build_args=['-Wno-fatal'], build_dir=build,
             timescale=('1ns', '1ps'), waves=a.waves)
runner.test(hdl_toplevel='fifo', test_module='test_fifo', test_dir=root,
            seed=a.seed, waves=a.waves, results_xml=str(build / 'results.xml'))
