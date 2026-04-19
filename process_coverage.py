#!/usr/bin/env python3
import json
import matplotlib.pyplot as plt

LOG_FILE = "coverage_timeline.jsonl"

def main():
    cumulative_blocks = set()
    unique_paths = set()

    iterations = []
    block_counts = []
    path_counts = []
    coverage_pct = []

    total_blocks = None

    with open(LOG_FILE, "r") as f:
        for line in f:
            run = json.loads(line)

            it = run["iteration"]
            blocks = run["blocks_hit"]
            total_blocks = run["total_blocks"]

            # ------------------------
            # Block coverage
            # ------------------------
            cumulative_blocks.update(blocks)
            current_blocks = len(cumulative_blocks)
            block_counts.append(current_blocks)

            # ------------------------
            # Coverage %
            # ------------------------
            pct = (current_blocks / total_blocks) * 100 if total_blocks else 0
            coverage_pct.append(pct)

            # ------------------------
            # Path coverage
            # ------------------------
            path_sig = tuple(blocks)
            unique_paths.add(path_sig)
            path_counts.append(len(unique_paths))

            iterations.append(it)

    # ------------------------
    # Combined Plot with % axis
    # ------------------------
    fig, ax1 = plt.subplots()

    # Left axis → counts
    ax1.plot(iterations, block_counts, label="Distinct Blocks", linewidth=2)
    ax1.plot(iterations, path_counts, label="Distinct Paths", linewidth=2)
    ax1.set_xlabel("Iteration")
    ax1.set_ylabel("Count")

    # Right axis → %
    ax2 = ax1.twinx()
    ax2.plot(iterations, coverage_pct, linestyle='--', label="Coverage %")
    ax2.set_ylabel("Coverage (%)")

    # ------------------------
    # Legends (merge both axes)
    # ------------------------
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2)

    plt.title("Coverage Growth Over Time")
    plt.grid()

    # ------------------------
    # FINAL % ANNOTATION
    # ------------------------
    final_pct = coverage_pct[-1] if coverage_pct else 0
    final_iter = iterations[-1] if iterations else 0

    ax2.annotate(
        f"Final Coverage: {final_pct:.2f}%",
        xy=(final_iter, final_pct),
        xytext=(final_iter * 0.7, final_pct * 0.9),
        arrowprops=dict(arrowstyle="->")
    )

    plt.savefig("coverage_combined.png")

    print(f"[+] Final coverage: {final_pct:.2f}%")
    print("[+] Plot saved: coverage_combined.png")


if __name__ == "__main__":
    main()