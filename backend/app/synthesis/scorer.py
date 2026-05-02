from app.models.finding import Finding
from app.models.report import ScoreBreakdown


SEVERITY_WEIGHTS = {
    "low": 15,
    "medium": 35,
    "high": 65,
    "critical": 90,
}


def score_findings(findings: list[Finding]) -> ScoreBreakdown:
    breakdown = ScoreBreakdown()

    for finding in findings:
        points = SEVERITY_WEIGHTS[finding.severity]
        if finding.source == "strava":
            breakdown.movement = min(100, breakdown.movement + points)
            breakdown.personnel = min(100, breakdown.personnel + points // 2)
        elif finding.source == "adsb":
            breakdown.aerial = min(100, breakdown.aerial + points)
        else:
            breakdown.facility = min(100, breakdown.facility + points)

    breakdown.aggregate = min(
        100,
        round(
            (
                breakdown.movement
                + breakdown.personnel
                + breakdown.facility
                + breakdown.aerial
            )
            / 4
        ),
    )
    return breakdown
