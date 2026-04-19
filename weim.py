#!/usr/bin/env python3
import sys
import os
import json
import subprocess
from pathlib import Path
import time

# ================= CONFIG =================
# Environment-based configuration
HARNESS_ROOT = os.getenv("HARNESS_ROOT_DIR", "/tmp")
CIDRIZE_BIN = os.getenv("HARNESS_TGT").split()
TIMEOUT = int(os.getenv("HARNESS_TIMEOUT", 5))
HARNESS_ARGS = os.getenv("HARNESS_ARGS","").split()

LOG_DIR = Path(HARNESS_ROOT) / "harness_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

HARNESS_ERROR_FILE = Path(HARNESS_ROOT) / "harness_error.txt"

# ================= FUNCTIONS =================
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
    """Log harness-level errors (do not trigger AFL bug)."""
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

# ================= MAIN =================
# ================= MAIN =================
def main():
    if len(sys.argv) < 2:
        log_harness_error("No input file specified")
        sys.exit(1)

    input_file = sys.argv[1]
    log_id = safe_log_id()

    # Read input as raw bytes
    try:
        input_bytes = Path(input_file).read_bytes()
        input_data = input_bytes.decode("latin-1").strip()
    except Exception as e:
        log_harness_error(f"Failed to read input file '{input_file}': {e}")
        return

    # Construct command from env
    if not CIDRIZE_BIN:
        log_harness_error("HARNESS_TGT not set")
        return

    cmd = CIDRIZE_BIN + HARNESS_ARGS + [input_data]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT
        )
    except FileNotFoundError:
        log_harness_error(f"Binary not found: {CIDRIZE_BIN}")
        return
    except PermissionError:
        log_harness_error(f"Binary permission denied: {CIDRIZE_BIN}")
        return
    except subprocess.TimeoutExpired:
        log_harness_error(f"Timeout expired for input file '{input_file}'")
        return
    except Exception as e:
        log_harness_error(f"Python exception while running binary: {e}")
        return

    output_text = (result.stdout or "") + (result.stderr or "")

    # Check for bugs
    if "No bugs found" not in output_text:
        log_bug(input_bytes, output_text, log_id)
        os.abort()

    if result.returncode != 0:
        log_bug(input_bytes, f"Non-zero return code: {result.returncode}\n{output_text}", log_id)
        os.abort()

if __name__ == "__main__":
    main()