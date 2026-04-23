#!/usr/bin/env python3
import os
import sys
import ast
import builtins
import importlib.abc
import importlib.machinery
import contextlib
import io
import json
import time
from pathlib import Path

# =====================================================================
# CONFIGURATION (Weim Logging Settings)
# =====================================================================
HARNESS_ROOT = os.getenv("HARNESS_ROOT_DIR", "/tmp")
LOG_DIR = Path(HARNESS_ROOT) / "harness_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
HARNESS_ERROR_FILE = Path(HARNESS_ROOT) / "harness_error.txt"
COVERAGE_TIMELINE_FILE = Path(HARNESS_ROOT) / "coverage_timeline.jsonl"
HARNESS_CHECK_EXIT_CODE = os.getenv("HARNESS_CHECK_EXIT_CODE", "0") == "1"

# =====================================================================
# 1. THE COVERAGE ENGINE (Dachshund)
# =====================================================================
class CoverageEngine:
    """Manages the high-speed memory map and coverage analytics."""
    def __init__(self, map_size=65536):
        self.map_size = map_size
        self.map = bytearray(self.map_size)
        self.block_counter = 0
        self.block_info = {}

        # Bind the high-speed hook globally so the AST can call it
        builtins._dachshund_cov = self._hit_hook

    def _hit_hook(self, block_id):
        self.map[block_id] = 1

    def register_block(self, module_name, description):
        """Allocates a new block ID for the AST rewriter."""
        self.block_counter += 1
        block_id = self.block_counter
        self.block_info[block_id] = f"{module_name} -> {description}"
        return block_id

    def reset(self):
        """Lightning-fast memory reset before the next execution."""
        self.map[:self.block_counter + 1] = b'\x00' * (self.block_counter + 1)

    def analyze_execution(self):
        """Returns the stats for the current memory map state."""
        hit_ids = [idx for idx in range(1, self.block_counter + 1) if self.map[idx]]
        total_blocks = self.block_counter
        coverage_pct = (len(hit_ids) / total_blocks * 100) if total_blocks else 0.0
        
        path_trace = [self.block_info[b] for b in hit_ids[-5:]]
        
        return {
            "hits": len(hit_ids),
            "total": total_blocks,
            "pct": coverage_pct,
            "trace": path_trace,
            "path": hit_ids  # ordered execution trace
        }


# =====================================================================
# 2. THE COMPILER ENGINE (AST Injection)
# =====================================================================
class ASTInjector(ast.NodeTransformer):
    """Rewrites Python syntax trees to inject coverage hooks."""
    def __init__(self, coverage_engine):
        self.cov = coverage_engine
        self.current_module = ""

    def _inject(self, body, description):
        block_id = self.cov.register_block(self.current_module, description)
        hit_node = ast.Expr(
            value=ast.Call(
                func=ast.Name(id='_dachshund_cov', ctx=ast.Load()),
                args=[ast.Constant(value=block_id)],
                keywords=[]
            )
        )
        return [hit_node] + body

    def visit_FunctionDef(self, node):
        node.body = self._inject(node.body, f"Func '{node.name}' (L{node.lineno})")
        return self.generic_visit(node)

    def visit_If(self, node):
        node.body = self._inject(node.body, f"If True (L{node.lineno})")
        if node.orelse:
            node.orelse = self._inject(node.orelse, f"If False/Else (L{node.lineno})")
        return self.generic_visit(node)
        
    def visit_For(self, node):
        node.body = self._inject(node.body, f"For loop (L{node.lineno})")
        return self.generic_visit(node)
        
    def visit_While(self, node):
        node.body = self._inject(node.body, f"While loop (L{node.lineno})")
        return self.generic_visit(node)
        
    def visit_ExceptHandler(self, node):
        node.body = self._inject(node.body, f"Except block (L{node.lineno})")
        return self.generic_visit(node)

class AOTLoader(importlib.abc.Loader):
    def __init__(self, code_obj, full_path):
        self.code_obj = code_obj
        self.full_path = full_path

    def get_filename(self, fullname): return self.full_path
    def create_module(self, spec): return None 
    def exec_module(self, module): exec(self.code_obj, module.__dict__)

class AOTFinder(importlib.abc.MetaPathFinder):
    def __init__(self, compiled_modules):
        self.compiled_modules = compiled_modules

    def find_spec(self, fullname, path, target=None):
        if fullname in self.compiled_modules:
            code, is_pkg, full_path = self.compiled_modules[fullname]
            spec = importlib.machinery.ModuleSpec(
                fullname, AOTLoader(code, full_path), is_package=is_pkg
            )
            spec.has_location = True
            return spec
        return None

class ProjectCompiler:
    """Scans and pre-compiles the entire target directory."""
    def __init__(self, target_folder, coverage_engine):
        self.target_folder = os.path.abspath(target_folder)
        self.injector = ASTInjector(coverage_engine)
        self.compiled_modules = {}
        
        if self.target_folder not in sys.path:
            sys.path.insert(0, self.target_folder)

    def compile_everything(self):
        for root, _, files in os.walk(self.target_folder):
            if "__pycache__" in root: continue
            
            for file in files:
                if file.endswith('.py'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.target_folder)
                    mod_name = rel_path.replace(os.sep, '.')[:-3]
                    
                    is_pkg = False
                    if mod_name.endswith('.__init__'):
                        mod_name = mod_name[:-9]
                        is_pkg = True
                    elif mod_name == '__init__':
                        mod_name = os.path.basename(self.target_folder)
                        is_pkg = True

                    with open(full_path, 'r', encoding='utf-8') as f:
                        source = f.read()
                        
                    tree = ast.parse(source, filename=full_path)
                    self.injector.current_module = mod_name
                    instrumented_tree = self.injector.visit(tree)
                    ast.fix_missing_locations(instrumented_tree)
                    
                    code = compile(instrumented_tree, full_path, 'exec')
                    self.compiled_modules[mod_name] = (code, is_pkg, full_path)
                    
        sys.meta_path.insert(0, AOTFinder(self.compiled_modules))
        return self.compiled_modules


# =====================================================================
# 3. WEIM LOGGING ENGINE
# =====================================================================
def log_bug(input_bytes, output_data, log_id):
    """Log AFL-detected crashes with raw input preserved via latin-1."""
    log_file = LOG_DIR / f"log_{log_id:06d}.json"
    try:
        with open(log_file, "w") as f:
            json.dump({
                "input": input_bytes.decode("latin-1"),
                "output": output_data,
                "timestamp": time.time(),
                "iteration": log_id
            }, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            write_id(log_id + 1)
    except Exception as e:
        log_harness_error(f"Failed to write bug log: {e}")

def write_id(logid):
    with open(Path(HARNESS_ROOT) / ".lid", "w") as f:
        f.write(str(logid))

def log_harness_error(msg):
    try:
        with open(HARNESS_ERROR_FILE, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        print(f"[Critical Harness Error] {msg}", file=sys.stderr)

def safe_log_id():
    lid_file = Path(HARNESS_ROOT) / ".lid"
    if not lid_file.exists():
        return 0
    with open(lid_file, "r") as f:
        return int(f.read())
    return 0
def get_and_increment_id():
    """Gets the current run ID and immediately increments it."""
    lid_file = Path(HARNESS_ROOT) / ".lid"
    current_id = 0
    if lid_file.exists():
        with open(lid_file, "r") as f:
            content = f.read().strip()
            if content:
                current_id = int(content)
    
    # Write the next ID back to disk
    with open(lid_file, "w") as f:
        f.write(str(current_id + 1))
        
    return current_id

def log_coverage_timeline(log_id, stats):
    """Appends the exact blocks hit in this run to a running JSONL file."""
    try:
        with open(COVERAGE_TIMELINE_FILE, "a") as f:
            record = {
                "iteration": log_id,
                "timestamp": time.time(),
                "total_blocks": stats["total"],
                "blocks_hit": stats["path"]  # List of block IDs hit this run
            }
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass # Fail silently so we don't break the fuzzer

# =====================================================================
# 4. AFL++ EXECUTION ENGINE
# =====================================================================
def execute_afl_run(target_dir, main_module, harness_func):
    if len(sys.argv) < 2:
        log_harness_error("No input file specified by AFL++")
        sys.exit(1)

    input_file = sys.argv[1]
    #log_id = safe_log_id()
    log_id = get_and_increment_id()
    # Read AFL++ mutated input
    try:
        input_bytes = Path(input_file).read_bytes()
        payload = input_bytes.decode("latin-1").strip()
    except Exception as e:
        log_harness_error(f"Failed to read input file '{input_file}': {e}")
        return

    # 1. Boot up Dachshund coverage and AOT compilation
    coverage = CoverageEngine()
    compiler = ProjectCompiler(target_dir, coverage)
    compiled_modules = compiler.compile_everything()

    if main_module not in compiled_modules:
        log_harness_error(f"Main module '{main_module}' not found in target dir.")
        sys.exit(1)

    main_code = compiled_modules[main_module][0]

    # 2. Reset coverage and set environment
    coverage.reset()
    namespace = {
        "__name__": "__main__", 
        "__file__": f"{main_module}.py",
        "__package__": ""  
    }

    # 3. Call the user's custom harness function to setup arguments
    harness_func(payload)

    error_msg = ""
    f = io.StringIO()

    # 4. Silent In-Process Execution
    # 4. Silent In-Process Execution
    with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        try:
            exec(main_code, namespace)
        except SystemExit as e:
            # If the script calls sys.exit(0) or sys.exit(None), it's a success.
            # If it calls sys.exit(1) AND our new flag is enabled, we log it as a bug!
            exit_code = e.code if e.code is not None else 0
            if HARNESS_CHECK_EXIT_CODE and exit_code != 0:
                error_msg = f"Fatal Exit Code Detected: {exit_code}"
        except Exception as e:
            # Standard Python exceptions are always treated as crashes
            error_msg = f"Crash: {type(e).__name__}: {e}"

    output_text = f.getvalue()

    # 5. Output Coverage Analytics
    stats = coverage.analyze_execution()

    # LOG THIS RUN TO THE JSONL TIMELINE
    log_coverage_timeline(log_id, stats)
    
    # Build a formatted coverage string
    cov_str = f"\n[*] Dachshund Coverage Results\n"
    cov_str += f"    Hits: {stats['hits']}/{stats['total']} ({stats['pct']:05.2f}%)\n"
    if stats['trace']:
        cov_str += "    Path Trace:\n"
        for path in stats['trace']:
            cov_str += f"     -> {path}\n"
    cov_str += "-" * 80

    # Print it (visible only when running standalone)
    #print(cov_str)

    # 6. Weim's Custom Bug Evaluation Rules
    bug_found = False
    if error_msg:
        bug_found = True
        output_text += f"\n[Harness Caught Exception]\n{error_msg}"
        
    elif not HARNESS_CHECK_EXIT_CODE and "No bugs found" not in output_text:
        bug_found = True
        output_text += "\n[Harness Alert] 'No bugs found' missing from output"

    # APPEND COVERAGE TO THE LOG OUTPUT
    output_text += f"\n\n{cov_str}"

    # 7. Register the crash with AFL++ using os.abort()
    if bug_found:
        log_bug(input_bytes, output_text, log_id)
        os.abort()  # Tell AFL++ "we found a crash!"


# =====================================================================
# 5. THE DYNAMIC HARNESS CONFIGURATION
# =====================================================================
if __name__ == "__main__":
    import shlex

    # --- 1. Read Target from run_weim.sh Environment ---
    target_path = os.getenv("HARNESS_TGT")
    if not target_path:
        log_harness_error("HARNESS_TGT environment variable is not set! Did you run run_iggy.sh?")
        print("[!] Error: HARNESS_TGT not set.", file=sys.stderr)
        sys.exit(1)

    # Automatically figure out the directory and module name
    target_path = os.path.abspath(target_path)
    TARGET_DIR = os.path.dirname(target_path)
    
    filename = os.path.basename(target_path)
    MAIN_MODULE = filename[:-3] if filename.endswith('.py') else filename
    
    # --- 2. Read Arguments from run_weim.sh Environment ---
    harness_args_env = os.getenv("HARNESS_ARGS", "")
    extra_args = shlex.split(harness_args_env) # Safely splits string into list (respects quotes)

    # --- 3. The Harness ---
    def target_harness(payload):
        # Dynamically build sys.argv
        # e.g., ["json_decoder_stv.py", "--str-json", payload]
        sys.argv = [filename] + extra_args + [payload]

    # --- Start the AFL++ Run ---
    execute_afl_run(TARGET_DIR, MAIN_MODULE, target_harness)