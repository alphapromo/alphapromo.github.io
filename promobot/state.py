"""Estado do robô, guardado no próprio repositório (pasta state/)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT

STATE = ROOT / "state"


def _read(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def plan_path(d: date) -> Path:
    return STATE / f"plano-{d.isoformat()}.json"


def load_plan(d: date) -> dict | None:
    return _read(plan_path(d), None)


def save_plan(d: date, plan: dict) -> None:
    _write(plan_path(d), plan)


def load_history() -> dict[str, str]:
    return _read(STATE / "historico.json", {})


def save_history(h: dict[str, str], hoje: date, manter_dias: int = 60) -> None:
    corte = (hoje - timedelta(days=manter_dias)).isoformat()
    _write(STATE / "historico.json", {k: v for k, v in h.items() if v >= corte})


def prune_plans(hoje: date, manter_dias: int) -> None:
    corte = hoje - timedelta(days=manter_dias)
    for p in STATE.glob("plano-*.json"):
        try:
            if date.fromisoformat(p.stem[6:]) < corte:
                p.unlink()
        except ValueError:
            pass
