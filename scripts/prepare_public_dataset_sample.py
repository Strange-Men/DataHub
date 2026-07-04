"""Convert a small public customer-support CSV sample to DataHub import JSON.

This script intentionally does not download datasets. Keep raw public dataset
files outside the repository, then pass their local path with --input.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a small public support dataset CSV to DataHub JSON.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a local CSV file, kept outside the repository.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the DataHub import JSON sample.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of customer-agent conversations to write.",
    )
    parser.add_argument(
        "--source-name",
        default="public_dataset_eval_bitext_sample",
        help="DataHub source_name value for the generated JSON.",
    )
    return parser.parse_args()


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _build_payload(csv_path: Path, source_name: str, limit: int) -> dict[str, object]:
    if limit < 1:
        raise ValueError("--limit must be at least 1.")
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    conversations: list[dict[str, object]] = []
    base_time = datetime(2026, 7, 3, 10, 0, 0)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"instruction", "response"}
        if not required.issubset(set(reader.fieldnames or [])):
            missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
            raise ValueError(f"Input CSV missing required columns: {missing}")

        for row in reader:
            question = _clean_text(row.get("instruction"))
            answer = _clean_text(row.get("response"))
            if not question or not answer:
                continue

            index = len(conversations) + 1
            timestamp = base_time + timedelta(minutes=index * 2)
            conversation_id = f"public_eval_conv_{index:03d}"
            conversations.append(
                {
                    "conversation_id": conversation_id,
                    "messages": [
                        {
                            "message_id": f"public_eval_msg_{index:03d}_customer",
                            "role": "customer",
                            "content": question,
                            "timestamp": timestamp.isoformat(),
                        },
                        {
                            "message_id": f"public_eval_msg_{index:03d}_agent",
                            "role": "agent",
                            "content": answer,
                            "timestamp": (timestamp + timedelta(minutes=1)).isoformat(),
                        },
                    ],
                }
            )
            if len(conversations) >= limit:
                break

    if not conversations:
        raise ValueError("No valid instruction/response rows found.")

    return {
        "source_name": source_name,
        "conversations": conversations,
    }


def main() -> int:
    args = _parse_args()
    payload = _build_payload(
        csv_path=Path(args.input),
        source_name=args.source_name,
        limit=args.limit,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    conversation_count = len(payload["conversations"])
    message_count = conversation_count * 2
    print(
        f"Wrote {conversation_count} conversations and {message_count} messages "
        f"to {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
