#!/usr/bin/env python3
"""Синтетический ДЫРЯВЫЙ инструмент: отдаёт валидный отчёт с находкой, verdict ПРОВАЛ, rc 1.

Проверяет способность loom поднять worst rc до 1 (мера умеет сказать «нет»).
"""
import argparse
import json
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", dest="json_path", required=True)
    p.add_argument("--in", dest="wired_in", default=None)
    p.add_argument("--target", default="target-провал")
    args, _ = p.parse_known_args()

    report = {
        "инструмент": {"имя": "подопытный_провал", "цель": args.target},
        "verdict": "ПРОВАЛ",
        "findings": [
            {"вердикт": "ПРОВАЛ", "вектор": "synthetic-hole",
             "почему": "нарочная дыра для доказательства, что loom ловит провал"},
        ],
        "получил_вход": args.wired_in,
        "почему": "дырявый синтетический инструмент — одна находка",
        "note": "synthetic broken tool",
    }
    with open(args.json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("[подопытный_провал] ПРОВАЛ (rc=1)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
