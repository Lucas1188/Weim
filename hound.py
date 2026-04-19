#!/usr/bin/env python3
import json
import re
from pathlib import Path
from collections import defaultdict

# ================= CONFIG =================
LOG_DIR = Path("harness_logs")
EXECINFO_DIR = Path("out/crashes")
OUTPUT_FILE = "final_bugs.json"

# ================= HELPERS =================
def extract_bug_section(output_text):
    start_marker = "Final bug count:"
    end_marker = "Saved bug count report and tracebacks for the bugs encountered!"

    idx_start = output_text.find(start_marker)
    if idx_start == -1:
        return None

    idx_end = output_text.find(end_marker, idx_start)
    if idx_end == -1:
        # fallback: just take till end
        return output_text[idx_start:]

    return output_text[idx_start:idx_end]

def parse_single_bug_from_output(output_text):
    """
    Parse a single bug tuple from 'Final bug count: defaultdict(...)' in one line.
    Returns (bug_type, exception, message, file, line, count) or None
    """
    m = re.search(
        r"Final bug count: defaultdict\(.*?,\s*\{\s*\("
        r"'(?P<bug_type>.*?)',\s*"
        r"<class '.*?\.(?P<exception>\w+)'>,\s*"
        r"(?P<quote>['\"])(?P<message>(?:\\.|(?!\1).)*)(?P=quote),\s*"
        r"'(?P<file>.*?)',\s*"
        r"(?P<line>\d+)\s*\)\s*:\s*"
        r"(?P<count>\d+)\s*\}\)",
        output_text,
        re.DOTALL
    )

    if not m:
        return parse_single_bug_from_output_structured(output_text)

    bug_type = m.group("bug_type")
    exception = m.group("exception")
    message = m.group("message")
    file_path = m.group("file")
    line_no = int(m.group("line"))
    count = int(m.group("count"))

    return (bug_type, exception, message, file_path, line_no, count)

def parse_single_bug_from_output_structured(output_text):
    if "Final bug count:" not in output_text:
        return None

    try:
        start = output_text.index("{")
        end = output_text.index("}", start)
        content = output_text[start+1:end].strip()

        tuple_part, count_part = content.rsplit(":", 1)
        count = int(count_part.strip())

        bug_type = tuple_part.split(",", 1)[0].strip(" ('")

        exc_match = re.search(r"\.(\w+)'>", tuple_part)
        exception = exc_match.group(1) if exc_match else "Unknown"

        file_matches = re.findall(r"'([^']+)'", tuple_part)
        file_path = file_matches[-1] if file_matches else ""

        line_match = re.search(r",\s*(\d+)\s*\)?\s*$", tuple_part)
        line_no = int(line_match.group(1)) if line_match else 0

        exc_end = tuple_part.find(">") + 1
        file_start = tuple_part.rfind(f"'{file_path}'")

        message = tuple_part[exc_end:file_start].strip().strip(",").strip()

        if message.startswith(("'", '"')) and message.endswith(("'", '"')):
            message = message[1:-1]

        return (bug_type, exception, message, file_path, line_no, count)

    except Exception:
        return None
#
# ================= MAIN =================
def main():
    # Dictionary to store first occurrence of each distinct bug
    # Keyed by (exception_class, file, line, bug_type)
    distinct_bugs = {}
    exec_info = {}
    for exec_infof in EXECINFO_DIR.glob("*"):
        
        # Match AFL-style filename pattern
        # e.g. id:000000,sig:06,src:000000,time:18680,execs:43,op:havoc,rep:2
        m_id = re.search(r'id:(\d+)', exec_infof.name)
        m_execs = re.search(r'execs:(\d+)', exec_infof.name)
        m_time = re.search(r'time:(\d+)',exec_infof.name)
        if m_id and m_execs:
            crash_id = int(m_id.group(1))
            execs = int(m_execs.group(1))
            t = int(m_time.group(1))
            exec_info[crash_id] = (execs,t)
    print(f"Size of crashes: {len(exec_info)}")
    p_error = 0
    for log_file in LOG_DIR.glob("*.json"):  # or "logs_*.json" if prefixed
        #print("Processing:", log_file)
        try:
            with open(log_file) as f:
                data = json.load(f)
        except Exception as e:
            print("Failed to load:", log_file, e)
            continue
        
        input_str = data.get("input", "")
        timestamp = data.get("timestamp", "")
        iteration = data.get("iteration", -1)
        op = data.get("output","")
        # Parse bug counts
        bug_section = extract_bug_section(op)

        if not bug_section:
            continue
        
        bug = parse_single_bug_from_output(bug_section)

        if bug:
            bug_type, exc_class, message, file_path, line_no, count = bug
            key = (exc_class, file_path, line_no, bug_type)
            # Store only the first occurrence
            if key not in distinct_bugs and iteration in exec_info:
                distinct_bugs[key] = {
                    "exception": exc_class,
                    "line": line_no,
                    "file": file_path,
                    "bug_type": bug_type,
                    "mutated_input": input_str,
                    "status": "bug",
                    "iteration": exec_info[iteration][0],
                    "datetime_executed": timestamp
                }
            else:
                if key in distinct_bugs and distinct_bugs[key]['iteration']>iteration:
                    distinct_bugs[key]['iteration'] = iteration
                    distinct_bugs[key]['mutated_input'] = input_str
                    distinct_bugs[key]['datetime_executed'] = timestamp
        else:
            print(f"Could not parse {bug_section}")
            p_error +=1
    if p_error:
        print(f"Could not parse {p_error} statements!")

    # Convert to list
    final_out = list(distinct_bugs.values())

    # Write to JSON
    with open(OUTPUT_FILE, "w") as f:
        json.dump(final_out, f, indent=2)

    print(f"[+] Wrote {len(final_out)} distinct bugs to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    import json

    log_file = "coverage_timeline.jsonl"
    cumulative_blocks = set()
    data_points = []

    with open(log_file, "r") as f:
        for line in f:
            run_data = json.loads(line)
            
            # Add the blocks hit in this run to our cumulative set
            cumulative_blocks.update(run_data["blocks_hit"])
            
            # Calculate the current cumulative coverage percentage
            total_possible = run_data["total_blocks"]
            current_coverage_pct = (len(cumulative_blocks) / total_possible) * 100
            
            data_points.append({
                "iteration": run_data["iteration"],
                "cumulative_pct": current_coverage_pct
            })

    print("Coverage Rate Over Time:")
    for pt in data_points[::100]: # Print every 100th run to keep it readable
        print(f"Run {pt['iteration']:05d} -> Coverage: {pt['cumulative_pct']:.2f}%")