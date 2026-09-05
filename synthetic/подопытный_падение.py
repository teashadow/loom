#!/usr/bin/env python3
"""Синтетический ПАДАЮЩИЙ инструмент: НЕ отдаёт валидный JSON, пишет мусор в stderr, rc 2.

Проверяет fail-safe loom: выход дропается и помечается, но пайплайн ПРОДОЛЖАЕТСЯ.
Пишем в --json битый текст (не JSON) — как реальный инструмент, упавший на середине записи.
"""
import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", dest="json_path", required=True)
    p.add_argument("--in", dest="wired_in", default=None)
    args, _ = p.parse_known_args()

    # инструмент «упал» посреди записи отчёта — на диске битый, невалидный JSON
    with open(args.json_path, "w", encoding="utf-8") as f:
        f.write('{"инструмент": {"имя": "подопытный_падение", НЕДОПИСАНО')
    print("[подопытный_падение] traceback: смоделированный сбой инструмента", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
