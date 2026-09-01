from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    args = parser.parse_args()
    repeat = int(os.environ.get("RESEARCH_AGENT_REPEAT_INDEX", "0"))
    metrics = {
        "success_rate": round(0.82 + repeat * 0.01, 4),
        "runtime_cost": round(1.5 + repeat * 0.05, 4),
    }
    with open(args.metrics, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
