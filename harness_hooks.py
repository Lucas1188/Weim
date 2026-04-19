# harness_hooks.py
import json

def __harness_log_state__(func_name, local_vars):
    # Filter out builtins to keep logs clean
    clean_vars = {k: str(v) for k, v in local_vars.items() if not k.startswith('__')}
    log_entry = {
        "event": "function_entry",
        "function": func_name,
        "state": clean_vars
    }
    print(f"[HARNESS-STATE] {json.dumps(log_entry)}")

def __harness_log_branch__(branch_id, direction):
    log_entry = {
        "event": "branch_taken",
        "branch_id": branch_id,
        "direction": direction
    }
    print(f"[HARNESS-CFG] {json.dumps(log_entry)}")