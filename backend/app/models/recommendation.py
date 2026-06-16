"""
Phase 5 Task 2 — Operational Recommendation Engine. Rule-based only, no LLM
(explicit instruction). Rules live in `docs/recommendation_rules.yaml`,
loaded and applied here — keeping the actual policy in a reviewable data
file rather than hardcoded in Python, so a non-engineer can audit/edit the
rules without reading code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = PROJECT_ROOT / "docs" / "recommendation_rules.yaml"


@dataclass
class Recommendation:
    risk_band: str
    final_action: str
    escalated: bool
    escalation_rule: str | None
    vehicle_mix: str
    junction_history_flag: bool

    def to_dict(self) -> dict:
        return {
            "risk_band": self.risk_band,
            "action": self.final_action,
            "escalated": self.escalated,
            "escalation_rule": self.escalation_rule,
            "vehicle_mix": self.vehicle_mix,
            "junction_history_flag": self.junction_history_flag,
        }


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_vehicle_mix(vehicle_type: str, rules: dict) -> str:
    high = set(rules["vehicle_mix"]["high_obstruction_types"])
    low = set(rules["vehicle_mix"]["low_obstruction_types"])
    if vehicle_type in high:
        return "high_obstruction"
    if vehicle_type in low:
        return "low_obstruction"
    return "unknown"  # vehicle_type not in either list — treated as low-priority, not an error


def compute_junction_history_flag(junction_name: str, junction_historical_risk: float, rules: dict) -> bool:
    jh_rules = rules["junction_history"]
    if junction_name == jh_rules["exclude_category"]:
        return False  # "No Junction" default category never flags — see YAML comment on the data quirk
    return junction_historical_risk >= jh_rules["flag_threshold"]


def recommend(
    risk_band: str,
    vehicle_type: str,
    junction_name: str,
    junction_historical_risk: float,
    rules: dict | None = None,
) -> Recommendation:
    if rules is None:
        rules = load_rules()

    vehicle_mix = classify_vehicle_mix(vehicle_type, rules)
    junction_flag = compute_junction_history_flag(junction_name, junction_historical_risk, rules)

    base_action = rules["risk_bands"][risk_band]["action"]
    final_band = risk_band
    escalated = False
    escalation_rule_name = None

    for rule in rules["escalation_rules"]:
        cond = rule["when"]
        matches = (
            cond["risk_band"] == risk_band
            and (cond["vehicle_mix"] == vehicle_mix)
            and (cond["junction_history_flag"] == junction_flag)
        )
        if matches:
            final_band = rule["escalate_to"]
            escalated = True
            escalation_rule_name = rule["name"]
            break  # only one escalation step per recommendation, per YAML policy

    final_action = rules["risk_bands"][final_band]["action"] if escalated else base_action

    return Recommendation(
        risk_band=final_band,
        final_action=final_action,
        escalated=escalated,
        escalation_rule=escalation_rule_name,
        vehicle_mix=vehicle_mix,
        junction_history_flag=junction_flag,
    )
