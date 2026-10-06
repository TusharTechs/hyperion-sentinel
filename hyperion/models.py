"""Finding model and the deterministic Edge Readiness score."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "GOOD"]
SAFE_AUTO, CONFIRM_REQUIRED, MANUAL_ONLY = "SAFE_AUTO", "CONFIRM_REQUIRED", "MANUAL_ONLY"

PENALTY = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 7, "LOW": 3, "GOOD": 0}
# Repeats of the same rule are discounted so one systemic gap cannot zero the score.
REPEAT_FACTORS = [1.0, 0.5, 0.25]  # 1st, 2nd, 3rd+ occurrence of a rule id


@dataclass
class Finding:
    rule: str
    severity: str
    category: str
    file: str
    finding: str
    evidence: str
    why_it_matters: str
    recommended_fix: str
    automation_safety: str = MANUAL_ONLY
    line: int | None = None
    end_line: int | None = None
    fix: dict = field(default_factory=dict)  # parameters for the remediation engine

    @property
    def key(self) -> str:
        """Stable identity used to compare findings before/after remediation."""
        return f"{self.rule}|{self.file}|{self.fix.get('target', '')}"

    def to_dict(self) -> dict:
        return asdict(self)


TIER_CAP = {"CRITICAL": 50, "HIGH": 36, "MEDIUM": 20, "LOW": 9, "GOOD": 0}  # max points one severity tier can cost


def compute_score(findings: list[Finding]) -> int:
    """100 minus severity penalties.

    Per finding: CRITICAL 25, HIGH 15, MEDIUM 7, LOW 3. A repeated rule counts 100%/50%/25%
    (3rd and later), and each severity tier is capped (see TIER_CAP), so one systemic gap or a
    long tail of small issues cannot zero the score. Floor 0. Deterministic: same findings, same score.
    """
    seen: dict[str, int] = {}
    tier = {s: 0.0 for s in SEVERITIES}
    for f in sorted(findings, key=lambda x: SEVERITIES.index(x.severity)):
        n = seen.get(f.rule, 0)
        seen[f.rule] = n + 1
        tier[f.severity] += PENALTY[f.severity] * REPEAT_FACTORS[min(n, len(REPEAT_FACTORS) - 1)]
    total = sum(min(v, TIER_CAP[s]) for s, v in tier.items())
    return max(0, round(100 - total))


@dataclass
class Report:
    score: int
    findings: list[Finding]  # issues, ordered by severity then file/line
    good: list[Finding]
    files_inspected: list[str]
    skipped: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in SEVERITIES[:4]}
        for f in self.findings:
            out[f.severity] += 1
        return out
