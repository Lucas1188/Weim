#!/usr/bin/env python3
import os
import sys
import marshal
import dis
import subprocess
import shutil
from pathlib import Path

# =====================================================================
# 0. THE HARD STOP (Enforce Python 3.12)
# =====================================================================
if sys.version_info.major != 3 or sys.version_info.minor != 12:
    print(f"[!] FATAL ERROR: You are running Python {sys.version_info.major}.{sys.version_info.minor}")
    print("[!] PyInstxtractor WILL FAIL to extract the PYZ archive on this version.")
    print("[!] Please run this in your terminal first: pyenv shell 3.12.0")
    sys.exit(1)

# =====================================================================
# 1. EXTRACTION
# =====================================================================
def run_extraction(bin_path):
    bin_file = Path(bin_path).resolve()
    target_dir = bin_file.parent
    
    print(f"[*] Attempting extraction of {bin_file.name}...")
    print(f"[*] Working directory: {target_dir}")
    
    # 1. Try it as a pip module (lowercase!)
    print("[*] Method A: Trying 'python3 -m pyinstxtractor'...")
    result = subprocess.run(
        [sys.executable, "-m", "pyinstxtractor", str(bin_file)],
        cwd=str(target_dir), 
        capture_output=True, text=True
    )
    
    # 2. If the module fails, try looking for a local pyinstxtractor.py script
    if result.returncode != 0:
        # Resolve the absolute path of wherever poodle.py was executed from
        local_script = Path.cwd() / "pyinstxtractor.py"
        print(f"[-] Method A failed. Method B: Trying local script at {local_script}...")
        
        if local_script.exists():
            result = subprocess.run(
                [sys.executable, str(local_script), str(bin_file)],
                cwd=str(target_dir),
                capture_output=True, text=True
            )
        else:
            print("[-] FATAL: Could not find the pip module OR a local pyinstxtractor.py script.")
            print("    Please run: pip install pyinstxtractor")
            sys.exit(1)

    # 3. Check for success
    if "Successfully extracted" in result.stdout:
        print("[+] Primary extraction successful.")
    else:
        print(f"[-] Extraction Error:\n{result.stdout}\n{result.stderr}")
        sys.exit(1) # Kill the script before it tries to search missing directories
# =====================================================================
# 2. SEARCH & DISASSEMBLE
# =====================================================================
def recursive_disassemble(directory, target_base_name):
    extract_path = Path(directory)
    print(f"[*] Searching recursively for: *{target_base_name}*")
    
    if not extract_path.exists():
        print(f"[-] CRITICAL: Directory does not exist: {extract_path}")
        return

    candidates = list(extract_path.rglob(f"*{target_base_name}*"))

    if candidates:
        target_file = candidates[0]
        output_path = target_file.with_suffix('.disasm')
        print(f"[*] Found target: {target_file}")
        
        try:
            with open(target_file, 'rb') as f:
                f.read(16) # Skip 3.12 Header
                code_obj = marshal.load(f)
                
            with open(output_path, 'w') as out:
                dis.dis(code_obj, file=out)
            print(f"[+] Disassembly saved to: {output_path}")
        except Exception as e:
            print(f"[-] Disassembly failed (might not be a valid .pyc): {e}")
            
    else:
        print(f"[-] Critical: No files matching '{target_base_name}' found.")
        print(f"[*] Dumping contents of {extract_path.name}:")
        for p in extract_path.iterdir():
            if p.is_dir():
                print(f"  [DIR]  {p.name}")
            else:
                print(f"  [FILE] {p.name}")

if __name__ == "__main__":
    # CONFIG
    BINARY = "/home/fgrgr5r/Documents/Weim/targets/IPv4-IPv6-parser/bin/linux-ipv6-parser"
    ENTRY_BASE = "ipv6_parser"  # Base name to search for in the extracted .pyc files
    
    base_dir = Path(BINARY).resolve().parent
    extract_dir = base_dir / "linux-ipv6-parser_extracted" 
    
    run_extraction(BINARY)
    recursive_disassemble(extract_dir, ENTRY_BASE)