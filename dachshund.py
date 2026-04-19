#!/usr/bin/env python3
import os
import sys
import ast
import builtins
import importlib.abc
import importlib.machinery
import contextlib
import io
import os
import ast
from pathlib import Path
# =====================================================================
# 1. THE COVERAGE ENGINE (Memory & Analytics)
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
        # We only clear the slice of memory we actually allocated
        self.map[:self.block_counter + 1] = b'\x00' * (self.block_counter + 1)

    def analyze_execution(self):
        """Returns the stats for the current memory map state."""
        hit_ids = [idx for idx in range(1, self.block_counter + 1) if self.map[idx]]
        total_blocks = self.block_counter
        coverage_pct = (len(hit_ids) / total_blocks * 100) if total_blocks else 0.0
        
        # Get the last 5 human-readable paths for context
        path_trace = [self.block_info[b] for b in hit_ids[-5:]]
        
        return {
            "hits": len(hit_ids),
            "total": total_blocks,
            "pct": coverage_pct,
            "trace": path_trace,
            "raw_blocks": hit_ids
        }


# =====================================================================
# 2. THE COMPILER ENGINE (AST & Import Hijacking)
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

# --- AOT Import Hook Classes ---
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
        print(f"[*] AOT Compiling directory: {self.target_folder}")
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
# 3. THE FUZZER ENGINE (Execution & Crash Catching)
# =====================================================================
class FuzzEngine:
    """Drives the execution loop and delegates target setup to the Harness."""
    def __init__(self, coverage_engine, compiled_modules):
        self.cov = coverage_engine
        self.compiled_modules = compiled_modules

    def run(self, main_module_name, harness_func, corpus):
        print(f"\n[*] Starting Fuzz Loop on: {main_module_name}")
        print("="*80)
        
        if main_module_name not in self.compiled_modules:
            print(f" [!] Error: Main module '{main_module_name}' not found.")
            return

        main_code = self.compiled_modules[main_module_name][0]

        for i, payload in enumerate(corpus):
            # 1. Reset Environment & Coverage
            self.cov.reset()
            
            namespace = {
                "__name__": "__main__", 
                "__file__": f"{main_module_name}.py",
                "__package__": ""  
            }
            
            # 2. Let the user's Harness configure the payload (e.g. sys.argv)
            harness_func(payload)
            
            error_msg = ""
            
            # 3. Silent Execution
            f = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                try:
                    exec(main_code, namespace)
                except SystemExit as e:
                    error_msg = f"SystemExit({e.code})"
                except Exception as e:
                    error_msg = f"Crash: {type(e).__name__}: {e}"

            # 4. Delegate Analysis to Coverage Engine
            stats = self.cov.analyze_execution()
            
            # 5. Reporting
            status = error_msg if error_msg else "OK"
            print(f"[{i}] Input: {repr(payload)[:25]:<27} | Hits: {stats['hits']:>3}/{stats['total']} ({stats['pct']:05.2f}%) | Status: {status}")
            
            if stats['trace']:
                print("    Path Trace:")
                for path in stats['trace']:
                    print(f"     -> {path}")
            print("-" * 80)


# =====================================================================
# 4. THE USER CONFIGURATION (The Harness)
# =====================================================================
if __name__ == "__main__":
    
    # --- Configuration ---
    TARGET_DIR = "/home/fgrgr5r/Documents/Weim/targets/json-decoder"
    MAIN_MODULE = "json_decoder_stv" 
    
    # --- The Harness ---
    # This defines exactly how the fuzzer should feed data to your specific target.
    # If a future target uses environment variables, you just change this function!
    def target_harness(payload):
        sys.argv = ["json_decoder_stv.py", "--str-json", payload]

    # --- The Corpus ---
    test_corpus = [
        '{"valid": "json"}',
        '{"broken: json',
        'None',
        '[1, 2, 3]',
        '{"A" * 1000: "buffer_test"}'
    ]
    
    # --- Bootstrapping the Architecture ---
    coverage = CoverageEngine()
    
    compiler = ProjectCompiler(TARGET_DIR, coverage)
    compiled_modules = compiler.compile_everything()
    
    fuzzer = FuzzEngine(coverage, compiled_modules)
    
    # Start the engine
    fuzzer.run(MAIN_MODULE, harness_func=target_harness, corpus=test_corpus)