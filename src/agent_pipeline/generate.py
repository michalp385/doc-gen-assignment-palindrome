"""Generate an advice report for a client.

Usage:
    python -m agent_pipeline.generate --client client_01_clean
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from agent_pipeline import pipeline
from agent_pipeline.config import load_report_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an advice report for a client.")
    parser.add_argument("--client", required=True, help="folder name under data/")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("config/template_config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--fresh", action="store_true", help="bypass the LLM cache and rewrite its entries"
    )
    parser.add_argument(
        "--estimate", action="store_true", help="print an uncached-call cost estimate, no calls"
    )
    args = parser.parse_args()

    load_dotenv()
    config = load_report_config(args.config)
    client_dir = args.data_dir / args.client
    pipeline.run(
        client_dir,
        config,
        outputs_dir=args.output_dir,
        fresh=args.fresh,
        estimate=args.estimate,
    )


if __name__ == "__main__":
    main()
