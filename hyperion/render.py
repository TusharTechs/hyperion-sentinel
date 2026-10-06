"""Human-readable rendering of analyzer facts. All numbers/evidence come from the analyzer, never the LLM."""

from __future__ import annotations

from .models import CONFIRM_REQUIRED, MANUAL_ONLY, SAFE_AUTO, Finding, Report, SEVERITIES
from .remediation import fixable

TAG = {SAFE_AUTO: "safe fix", CONFIRM_REQUIRED: "needs your OK", MANUAL_ONLY: "manual"}
ORD = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]
SHOW_LIMIT = 15


def effective_safety(f: Finding) -> str:
    """A finding is only auto-fixable when a fixer exists for it."""
    if f.automation_safety in (SAFE_AUTO, CONFIRM_REQUIRED) and not fixable(f):
        return MANUAL_ONLY
    return f.automation_safety


def where(f: Finding) -> str:
    if f.file in ("", "(workspace)"):
        return "workspace"
    return f"{f.file}:{f.line}" if f.line else f.file


def counts_line(report: Report) -> str:
    c = report.counts()
    parts = [f"{n} {s}" for s, n in c.items() if n]
    return " · ".join(parts) if parts else "no issues"


def automation_counts(findings: list[Finding]) -> tuple[int, int, int]:
    s = sum(1 for f in findings if effective_safety(f) == SAFE_AUTO)
    c = sum(1 for f in findings if effective_safety(f) == CONFIRM_REQUIRED)
    return s, c, len(findings) - s - c


def report_text(report: Report, findings: list[Finding], full: bool = False) -> str:
    n_files = len(report.files_inspected)
    lines = ["EDGE READINESS REPORT", "",
             f"Edge Readiness: {report.score}/100   (Sentinel's own heuristic - not an official HYPER-AI metric)", "",
             f"I inspected {n_files} deployment-related file{'s' if n_files != 1 else ''}"
             + (f": {', '.join(report.files_inspected[:8])}{'…' if n_files > 8 else ''}" if n_files else "") + ".",
             f"{len(findings)} finding{'s' if len(findings) != 1 else ''}: {counts_line(report)}", ""]
    shown = findings if full else findings[:SHOW_LIMIT]
    for i, f in enumerate(shown, 1):
        lines.append(f"{i:>2}. {f.severity:<8} {f.finding}  [{where(f)}] ({TAG[effective_safety(f)]})")
    if len(findings) > len(shown):
        lines.append(f"    …and {len(findings) - len(shown)} more (say \"list all issues\").")
    if report.good:
        lines += ["", "Already good:"] + [f"  ✓ {g.finding}" for g in report.good[:6]]
    if report.skipped:
        lines += ["", f"Skipped {len(report.skipped)} file(s): {', '.join(report.skipped[:3])}"]
    s, c, m = automation_counts(findings)
    if findings:
        lines += ["", narrative(report, findings), "",
                  f"I can fix {s} safely, {c} need your confirmation, and {m} are manual.",
                  "Ask \"what should I fix first?\" or say \"fix everything you safely can\"."]
    else:
        lines += ["", "Nothing to fix - this workspace looks edge-ready by Sentinel's checks."]
    return "\n".join(lines)


def narrative(report: Report, findings: list[Finding]) -> str:
    top = sorted(findings, key=lambda f: (SEVERITIES.index(f.severity), -int(effective_safety(f) == SAFE_AUTO)))[0]
    return (f"The highest-risk issue is in {top.file or 'the workspace'}: {top.finding}. "
            f"{top.why_it_matters}")


def priority_text(findings: list[Finding]) -> str:
    if not findings:
        return "There is nothing to fix right now. Ask me to analyze your workspace if you've changed files."
    rank = sorted(enumerate(findings, 1), key=lambda p: (SEVERITIES.index(p[1].severity),
                                                        0 if effective_safety(p[1]) == SAFE_AUTO else 1, p[0]))
    top = rank[:3]
    out = ["Here is what I'd fix first, highest impact first:", ""]
    for n, f in top:
        out += [f"#{n} {f.severity} - {f.finding} [{where(f)}]",
                f"   Why: {f.why_it_matters}",
                f"   Evidence: {f.evidence}" if f.evidence else "",
                f"   Fix: {f.recommended_fix} ({TAG[effective_safety(f)]})", ""]
    out.append(f"Say \"fix #{top[0][0]}\" for the first one, or \"fix everything you safely can\".")
    return "\n".join(out)


def detail_text(n: int, f: Finding) -> str:
    return "\n".join([f"Issue #{n} - {f.severity} ({f.category})", f"What: {f.finding}", f"Where: {where(f)}",
                      f"Evidence: {f.evidence}", f"Why it matters: {f.why_it_matters}",
                      f"Recommended fix: {f.recommended_fix}", f"Automation: {TAG[effective_safety(f)]}"])


def plan_text(safe: list[Finding], confirm: list[Finding], manual: list[Finding], summaries: dict[str, str]) -> str:
    out = ["REMEDIATION PLAN", ""]
    if safe:
        out.append("Safe changes")
        out += [f"  ✓ {summaries.get(f.key) or f.recommended_fix}" for f in safe]
    if confirm:
        out += ["", "Requires confirmation"]
        out += [f"  ⚠ {summaries.get(f.key) or f.recommended_fix}" for f in confirm]
    if manual:
        out += ["", "Manual (I won't touch these)"]
        out += [f"  • {f.finding} [{where(f)}] - {f.recommended_fix}" for f in manual[:8]]
        if len(manual) > 8:
            out.append(f"  • …and {len(manual) - 8} more")
    return "\n".join(out)


def score_explanation() -> str:
    return ("How the score works: it starts at 100 and subtracts a fixed penalty per finding - CRITICAL 25, HIGH 15, "
            "MEDIUM 7, LOW 3. Repeats of the same rule count 100%/50%/25%, and each severity tier has a cap "
            "(CRITICAL 50, HIGH 36, MEDIUM 20, LOW 9) so one systemic gap can't zero the score. It is computed by "
            "deterministic code from files in your workspace - the language model never sets it - and it is Sentinel's own "
            "heuristic, not an official HYPER-AI metric or a certification.")
