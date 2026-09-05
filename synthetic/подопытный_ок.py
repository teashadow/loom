#!/usr/bin/env python3
"""Синтетический ЗДОРОВЫЙ инструмент: отдаёт валидный отчёт, verdict ПРОШЁЛ, rc 0.

Отражает полученный по wire вход (--in) в поле report['получил_вход'] — это пруф, что
файловая связь loom реально передала значение из предыдущего шага.
"""
import argparse
import json
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", dest="json_path", required=True)
    p.add_argument("--in", dest="wired_in", default=None)
    p.add_argument("--target", default="target-ок")
    args, _ = p.parse_known_args()

    report = {
        "инструмент": {"имя": "подопытный_ок", "цель": args.target},
        "verdict": "ПРОШЁЛ",
        "findings": [],
        "получил_вход": args.wired_in,   # что пришло по wire из прошлого шага
        "почему": "здоровый синтетический инструмент — нечего чинить",
        "note": "synthetic OK tool",
    }
    with open(args.json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[подопытный_ок] ПРОШЁЛ; получил_вход={args.wired_in}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
