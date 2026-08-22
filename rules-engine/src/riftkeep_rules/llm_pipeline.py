from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .llm_interpretation import InterpretationStageResult, run_interpretation
from .llm_provider import JsonLlmProvider


M10_DISABLED_STAGE_ERROR = (
    "disabled by M10 capability policy: LLMs may interpret/decompose player language only; "
    "evidence completion, adjudication, and answer writing are not active capabilities"
)


@dataclass
class LlmStageResult:
    accepted: bool
    payload: dict[str, Any] | None
    errors: list[str]


class GroundedLlmPipeline:
    """M10 capability gate.

    Only ``interpret_question`` may call the provider. Legacy pre-M10 entry points are
    retained as fail-closed compatibility shims so an older caller cannot accidentally
    regain adjudication or answer-writing authority.
    """

    def __init__(self, provider: JsonLlmProvider | None):
        self.provider = provider

    def interpret_question(self, question: str) -> InterpretationStageResult:
        return run_interpretation(question, self.provider)

    def request_evidence_completion(self, packet: dict[str, Any]) -> LlmStageResult:
        return LlmStageResult(False, None, [M10_DISABLED_STAGE_ERROR])

    def adjudicate(self, packet: dict[str, Any]) -> LlmStageResult:
        return LlmStageResult(False, None, [M10_DISABLED_STAGE_ERROR])

    def draft_answer(self, adjudication: dict[str, Any], evidence_catalog: list[dict[str, Any]]) -> LlmStageResult:
        return LlmStageResult(False, None, [M10_DISABLED_STAGE_ERROR])


def make_adjudication_packet(engine_result: dict[str, Any]) -> dict[str, Any]:
    """Legacy M9-era packet builder retained for data migration/tests only.

    M10 runtime does not send this packet to an LLM. It remains readable so older
    serialized fixtures can be inspected without reintroducing provider authority.
    """
    issues = []
    catalog: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(engine_result.get("issues", []), 1):
        iid = f"I{idx}"
        issues.append({
            "issueId": iid,
            "question": item.get("issue"),
            "proofObligations": item.get("proof", {}).get("obligations", []),
            "knownEvidenceComplete": item.get("proof", {}).get("evidenceCompleteForKnownObligations", False),
        })
        for e in item.get("evidenceCatalog", []) or []:
            if e.get("evidenceId"):
                catalog[str(e["evidenceId"])] = e
    return {
        "question": engine_result.get("question"),
        "issues": issues,
        "facts": engine_result.get("facts", []),
        "scenarioLanguage": engine_result.get("scenarioLanguage", {}),
        "mentionedGameActions": engine_result.get("mentionedGameActions", []),
        "authorityStatus": engine_result.get("authorityStatus", {}),
        "evidenceCatalog": list(catalog.values()),
        "constraints": {
            "legacyPacketOnly": True,
            "notPermittedAsM10ProviderInput": True,
        },
    }
