# Weim AFL Wrapped Binary Harness

This repository provides a harness (`weim.py`), packager (`hound.py`) and a helper scripts (`run_weim.sh`), (`pack_logs.sh`) for fuzzing specifically wrapped target binaries with AFL.

---

## Prerequisites

- Python 3.8+
- AFL++ [American Fuzzy Lop++](https://aflplus.plus/building/)
- A compiled target binary (e.g., `cidrize-runner/bin/linux-cidrize-runner`)
- Bash shell (Linux/macOS)

---

## Files

| File | Description |
|------|-------------|
| `weim.py` | Python harness that runs the target binary on AFL inputs and logs bugs. |
| `run_weim.sh` | Bash script to set up environment variables and generate AFL commands. |
| `seeds/` | Directory for initial AFL seed inputs. |
| `out/` | AFL output directory. |
| `logs/` | Harness logs directory. |
| `final_bugs.json` | JSON file containing all logged bugs. |
| `harness_error.txt` | File containing any harness-level errors. |


## Usage

### Source the script
```
source ./run_weim.sh <target_binary> <timeout_per_input_sec> <max_fuzz_duration> "<harness_args>"
```
| Argument | Description |
|----------|-------------|
| `<target_binary>` | Path to the binary you want to fuzz.  |
| `<timeout_per_input_sec>` | Maximum time to allow each AFL input. |
| `<max_fuzz_duration>` | How long to fuzz (e.g., 4h, 10m). |
| `<harness_args>` | Arguments to pass to the target binary via the harness. |

### Example:
`
source ./run_weim.sh cidrize-runner/bin/linux-cidrize-runner 5 4h "--func cidrize --ipstr"
`

This sets the following environment variables in your shell vital for the afl driver code to work properly:
```
HARNESS_TGT
HARNESS_TIMEOUT
HARNESS_ARGS
HARNESS_ROOT_DIR
```

When AFL is complete, run ./pack_logs.sh to package all the relevant logs and parse distinct bugs
