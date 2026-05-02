SYSTEM_PROMPT = """
You are an OPSEC analyst producing a defensive threat brief from public-source traces.
Focus on what an adversary could infer, confidence level, likely collection path, and mitigations.
Do not recommend targeting or harmful action.
""".strip()


def build_synthesis_input(
    target_name: str,
    mode: str,
    score_summary: str,
    serialized_findings: str,
) -> str:
    return f"""
Target: {target_name}
Mode: {mode}
Exposure score summary: {score_summary}

Findings:
{serialized_findings}

Write a concise defensive threat brief with:
1. The strongest public signals an adversary could infer
2. A short confidence statement
3. The most relevant defensive mitigations

Stay grounded in the provided findings only.
""".strip()
