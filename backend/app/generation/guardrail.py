"""Truthfulness guardrail for AI-generated application documents.

Rule (from the architecture): a tailored resume / cover letter must not claim
any skill, employer, or credential that does not appear in the candidate's
source resume. The generator emphasizes and rephrases real facts; it never
invents.

`check_generated` returns violations — claims present in the output whose
supporting token is absent from the source. Callers reject or regenerate on
any violation, so nothing fabricated ever reaches an application.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")

# Curated skill/technology vocabulary we police for fabrication. A claim of
# one of these in the output must be backed by the source resume.
_POLICED_TERMS = {
    "python", "java", "javascript", "typescript", "go", "golang", "rust",
    "c++", "c#", "ruby", "scala", "kotlin", "php", "swift", "sql", "nosql",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "cassandra",
    "kafka", "spark", "hadoop", "airflow", "snowflake", "databricks",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "react", "angular", "vue", "svelte", "node.js", "nodejs", "spring",
    "django", "fastapi", "flask", "rails", "graphql", "grpc", "tensorflow",
    "pytorch", "pandas", "numpy", "jenkins", "gitlab", "circleci",
    "elasticsearch", "kibana", "grafana", "prometheus",
    "salesforce", "sap", "oracle", "tableau", "powerbi", "hive", "flink",
}

# Degree/credential phrases whose fabrication we also block.
_CREDENTIALS = re.compile(
    r"\b(ph\.?d|doctorate|mba|master'?s|bachelor'?s|b\.?s\.?|m\.?s\.?|"
    r"pmp|cissp|aws certified|azure certified|cpa)\b", re.I)


@dataclass
class GuardrailReport:
    ok: bool
    fabricated_skills: list[str]
    fabricated_credentials: list[str]


def _skill_tokens(text: str) -> set[str]:
    tokens = set()
    lowered = text.lower()
    for term in _POLICED_TERMS:
        if term in lowered:
            tokens.add(term)
    return tokens


def check_generated(source_resume: str, generated: str) -> GuardrailReport:
    source_skills = _skill_tokens(source_resume)
    output_skills = _skill_tokens(generated)
    fabricated_skills = sorted(output_skills - source_skills)

    source_creds = {m.group(0).lower() for m in _CREDENTIALS.finditer(source_resume)}
    fabricated_creds = sorted({
        m.group(0).lower() for m in _CREDENTIALS.finditer(generated)
    } - source_creds)

    return GuardrailReport(
        ok=not fabricated_skills and not fabricated_creds,
        fabricated_skills=fabricated_skills,
        fabricated_credentials=fabricated_creds)
