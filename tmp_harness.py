
import sys, os, marshal, builtins, io, contextlib, dis

# Setup Paths
abs_root = r"/home/fgrgr5r/Documents/Weim/tmp/cidrize-runner/bin/linux-cidrize-runner_extracted/PYZ-00.pyz_extracted"
pyz_dir = os.path.join(abs_root, "PYZ.pyz_extracted")
sys.path.insert(0, pyz_dir)
sys.path.insert(0, abs_root)

# Tracing Hook (Same as your current one)
seen_offsets = set()
def tracer(frame, event, arg):
    if event == 'opcode':
        print(f"COV:{os.path.basename(frame.f_code.co_filename)}:{frame.f_lasti}")
    return tracer

# Setup Args & Execute
sys.argv = ['poodle.py'] # Inherited from fuzzer
sys.settrace(tracer)
sys._getframe().f_trace_opcodes = True

with open(r"/home/fgrgr5r/Documents/Weim/tmp/cidrize-runner/bin/linux-cidrize-runner_extracted/cidrize_runner_stv.pyc", 'rb') as f:
    f.read(16)
    code = marshal.load(f)
    exec(code, {"__name__": "__main__", "__builtins__": builtins.__dict__})
