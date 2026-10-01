"""Kitsune regression subsystem. Extracted without changing the original function bodies."""

from .foundation import *

class RegressionGuard:
    def __init__(self):
        self.known_good = set()  # normalized commands that have exited 0 this session

    def record_result(self, command, success):
        normalized = re.sub(r"\s+", " ", command.strip())
        was_regression = success is False and normalized in self.known_good
        if success:
            self.known_good.add(normalized)
        return was_regression

def compute_confidence(verified_ok, regression_detected, similar_successes, similar_failures, sanity_issue_count=0):
    score = 50
    reasons = []
    if verified_ok:
        score += 25
        reasons.append("Verification/build passed")
    else:
        score -= 20
        reasons.append("Verification did not run or did not pass")
    if regression_detected:
        score -= 35
        reasons.append("Regression detected in previously-working behavior")
    else:
        reasons.append("No regressions detected")
    if similar_successes:
        score += min(15, similar_successes * 5)
        reasons.append(f"Similar past fix(es) to these file(s) succeeded ({similar_successes}x)")
    if similar_failures:
        score -= min(20, similar_failures * 7)
        reasons.append(f"Similar past fix(es) to these file(s) failed before ({similar_failures}x)")
    if sanity_issue_count:
        score -= min(15, sanity_issue_count * 5)
        reasons.append(f"Sanity check found {sanity_issue_count} issue(s) (config/dependency/memory integrity)")
    score = max(0, min(100, score))
    return score, reasons

