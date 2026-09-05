"""Рама конвейера: гоняет упорядоченные шаги как подпроцессы, связывает их файлами.

Контракт (общий для фреймворка mad-tools):
  спека пайплайна (JSON) = {"name": str, "steps": [шаг, ...]}
  шаг = {
    "tool":  "имя-для-отчёта",
    "cmd":   ["python3", "инструмент.py", "subcmd", ...],   # база команды (+ позиционные)
    "config": {"flag": "value", "bool_flag": true, ...},    # доп. опции → --flag value
    "wire":  {"in": "инструмент.цель"}                       # поле вывода ЭТОГО шага → вход СЛЕДУЮЩЕГО
  }

Каждый инструмент — подпроцесс. loom всегда добавляет `--json <tmp>` и читает оттуда
структурный отчёт инструмента. Код возврата берётся у процесса. worst rc = максимум по шагам.

🔴 Мера обязана уметь сказать «нет»: шаг с rc≥1 поднимает worst rc пайплайна. Шаг, не отдавший
валидный JSON, ДРОПАЕТСЯ (его выход не идёт дальше по wire) и ПОМЕЧАЕТСЯ, но пайплайн продолжает —
одна упавшая проба не должна ронять весь конвейер (fail-safe).

🔴 Связь между шагами ФАЙЛОВАЯ, не импорт: loom читает JSON-отчёт шага N с диска и по карте `wire`
достаёт значения, которые подаёт шагу N+1 как CLI-опции. Инструменты друг про друга не знают.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# rc-контракт фреймворка
RC_CLEAN = 0        # чисто
RC_FAIL = 1         # провал
RC_NOT_RUN = 2      # не состоялась (fail-safe: неизвестное = отказ)


def _dotted_get(данные: Any, путь: str) -> Any:
    """Достать значение по пути 'a.b.c' из вложенного dict/list. Нет пути → None."""
    cur = данные
    for кусок in путь.split("."):
        if isinstance(cur, dict):
            if кусок not in cur:
                return None
            cur = cur[кусок]
        elif isinstance(cur, list):
            try:
                cur = cur[int(кусок)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _config_to_args(config: dict[str, Any]) -> list[str]:
    """dict опций → список CLI-аргументов. True → голый флаг; list → повтор; иначе --k v."""
    args: list[str] = []
    for k, v in config.items():
        flag = f"--{k}" if not k.startswith("-") else k
        if v is True:
            args.append(flag)
        elif v is False or v is None:
            continue
        elif isinstance(v, (list, tuple)):
            for item in v:
                args.extend([flag, str(item)])
        else:
            args.extend([flag, str(v)])
    return args


def _count_findings(report: dict) -> int:
    """Сколько проблемных находок в отчёте инструмента (единый контракт семьи)."""
    n = 0
    for f in (report.get("findings") or report.get("пробы") or []):
        вердикт = str(f.get("вердикт") or f.get("класс") or "")
        if вердикт in ("ПРОВАЛ", "ВНИМАНИЕ", "критический", "высокий"):
            n += 1
    n += len(report.get("security_findings") or [])
    return n


def _find_finding_organizer(spec_path: Path) -> Any:
    """Попытаться подтянуть finding-organizer из соседнего каталога. Нет → None (не падать)."""
    рядом_со_спекой = spec_path.resolve().parent
    loom_корень = Path(__file__).resolve().parent.parent.parent
    # ищем finding-organizer как соседа спеки, её родителя и каталога loom
    базы = [рядом_со_спекой, рядом_со_спекой.parent, loom_корень]
    кандидаты = [база / "finding-organizer" for база in базы]
    for кан in кандидаты:
        if (кан / "fo" / "store.py").exists():
            if str(кан) not in sys.path:
                sys.path.insert(0, str(кан))
            try:
                from fo.store import ingest_tool_report  # type: ignore
                return ingest_tool_report
            except Exception:
                return None
    return None


def run_step(step: dict, wired_in: dict[str, Any], timeout: int) -> dict:
    """Прогнать один шаг как подпроцесс. Вернуть результат шага (со снятым отчётом или пометкой drop)."""
    tool = step.get("tool", "?")
    cmd = list(step.get("cmd") or [])
    if not cmd:
        return {"tool": tool, "cmd": [], "rc": RC_NOT_RUN, "dropped": True,
                "почему_drop": "пустая команда шага", "report_present": False,
                "findings_count": 0, "wired_in": wired_in}

    with tempfile.NamedTemporaryFile("r", suffix=".json", prefix="loom_", delete=False) as tf:
        out_path = Path(tf.name)

    полная = cmd + _config_to_args(step.get("config") or {}) + _config_to_args(wired_in)
    полная += ["--json", str(out_path)]

    результат: dict[str, Any] = {"tool": tool, "cmd": полная, "wired_in": wired_in}
    try:
        proc = subprocess.run(полная, capture_output=True, text=True, timeout=timeout)
        rc = proc.returncode
        stderr = (proc.stderr or "")[-500:]
    except FileNotFoundError as e:
        результат.update({"rc": RC_NOT_RUN, "dropped": True, "report_present": False,
                          "findings_count": 0, "почему_drop": f"нет исполнителя: {e}"})
        out_path.unlink(missing_ok=True)
        return результат
    except subprocess.TimeoutExpired:
        результат.update({"rc": RC_NOT_RUN, "dropped": True, "report_present": False,
                          "findings_count": 0, "почему_drop": f"таймаут {timeout}с"})
        out_path.unlink(missing_ok=True)
        return результат

    report: dict | None = None
    try:
        текст = out_path.read_text(encoding="utf-8")
        if текст.strip():
            report = json.loads(текст)
    except (OSError, json.JSONDecodeError):
        report = None
    finally:
        out_path.unlink(missing_ok=True)

    if not isinstance(report, dict):
        # 🔴 Шаг «упал»: код мог быть любой, но валидного JSON нет → выход ДРОПАЕМ и ПОМЕЧАЕМ,
        # по wire дальше ничего не идёт. Пайплайн продолжится следующим шагом.
        результат.update({"rc": rc, "dropped": True, "report_present": False,
                          "findings_count": 0,
                          "почему_drop": f"нет валидного JSON-отчёта (rc={rc})",
                          "stderr_хвост": stderr})
        return результат

    результат.update({"rc": rc, "dropped": False, "report_present": True,
                      "verdict": report.get("verdict", ""),
                      "findings_count": _count_findings(report),
                      "report": report})
    return результат


def run_pipeline(spec_path: str | Path, report_path: str | Path | None = None,
                 timeout: int = 120) -> dict:
    """Прогнать весь пайплайн. Вернуть агрегат-отчёт (в контракте семьи) с worst rc.

    worst_rc = максимум кодов возврата шагов. Дропнутые шаги помечены, но не рвут конвейер.
    Находки каждого живого отчёта скармливаются finding-organizer (если доступен), best-effort.
    """
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    steps = spec.get("steps") or []
    name = spec.get("name", spec_path.stem)

    ingest = _find_finding_organizer(spec_path)
    ingested_ids: list[str] = []

    шаги_итог: list[dict] = []
    все_находки: list[dict] = []
    worst_rc = RC_CLEAN
    dropped_count = 0
    wired_in: dict[str, Any] = {}

    for i, step in enumerate(steps):
        r = run_step(step, wired_in, timeout)
        worst_rc = max(worst_rc, int(r.get("rc", RC_NOT_RUN)))

        if r.get("dropped"):
            dropped_count += 1
            wired_in = {}  # с упавшего шага дальше ничего не связываем
        else:
            report = r["report"]
            # собрать находки этого шага в общий агрегат
            for f in (report.get("findings") or []):
                все_находки.append({**f, "шаг": i, "инструмент": step.get("tool", "?")})
            # finding-organizer: занести отчёт шага в общую БД (best-effort, не рушить loom)
            if ingest is not None:
                try:
                    for fnd in ingest(report):
                        ingested_ids.append(fnd.id)
                except Exception:
                    pass
            # 🔴 файловая связь: достать поля ЭТОГО отчёта по карте wire → вход СЛЕДУЮЩЕГО шага
            wired_in = {}
            for целевой_ключ, путь in (step.get("wire") or {}).items():
                значение = _dotted_get(report, путь)
                if значение is not None:
                    wired_in[целевой_ключ] = значение

        # отчёт шага без тяжёлого сырого report — его храним отдельно если нужно
        компакт = {k: v for k, v in r.items() if k != "report"}
        шаги_итог.append(компакт)

    провалов = sum(1 for s in шаги_итог if int(s.get("rc", 0)) == RC_FAIL)
    если_не_состоялось = sum(1 for s in шаги_итог if int(s.get("rc", 0)) >= RC_NOT_RUN)

    if worst_rc >= RC_NOT_RUN:
        verdict = "НЕ ПРОВЕРЕНО"
    elif worst_rc == RC_FAIL:
        verdict = "ПРОВАЛ"
    else:
        verdict = "ПРОШЁЛ"

    агрегат = {
        "инструмент": {"имя": "loom", "цель": name},
        "verdict": verdict,
        "worst_rc": worst_rc,
        "шагов": len(steps),
        "дропнуто": dropped_count,
        "провалов": провалов,
        "не_состоялось": если_не_состоялось,
        "findings": все_находки,
        "steps": шаги_итог,
        "finding_organizer": {
            "доступен": ingest is not None,
            "занесено_id": ingested_ids,
        },
        "почему": (f"шагов {len(steps)}, провалов {провалов}, дропнуто {dropped_count}; "
                   f"worst rc={worst_rc}"),
        "note": "loom — рама конвейера: подпроцессы + файловая связь wire + агрегат находок. "
                "Вердикт ставит код (worst rc), не модель.",
    }

    if report_path is not None:
        Path(report_path).write_text(
            json.dumps(агрегат, ensure_ascii=False, indent=2), encoding="utf-8")

    return агрегат
