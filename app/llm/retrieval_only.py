
"""Deterministic, grounded extractive answer provider for retrieval-only mode."""

import re
from typing import List, Tuple

from app.llm.base import BaseLLMProvider
from app.models import SearchResultItem


class RetrievalOnlyProvider(BaseLLMProvider):
    """Synthesize answers only from retrieved evidence."""

    @property
    def name(self) -> str:
        return "retrieval_only"

    @staticmethod
    def _clean_excerpt(text: str) -> str:
        """Remove retrieval markers while preserving Markdown list boundaries."""
        text = text.replace("[[", "").replace("]]", "")
        text = re.sub(r"^\s*\.\.\.\s*", "", text)
        text = re.sub(r"\s*\.\.\.\s*$", "", text)

        # Preserve line breaks so individual Markdown bullets remain separate.
        lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in text.splitlines()
        ]
        return "\n".join(line for line in lines if line).strip()

    @staticmethod
    def _extract_facts(text: str) -> List[str]:
        """Extract individual readable facts without inventing evidence."""
        parts = re.split(r"(?m)(?=^\s*[-*]\s+)", text)
        facts: List[str] = []

        for part in parts:
            cleaned = re.sub(r"^\s*(?:[-*]\s+|#{1,6}\s+|>\s*)", "", part).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)

            if len(cleaned) < 15:
                continue

            lowered = cleaned.lower()
            if any(
                phrase in lowered
                for phrase in (
                    "synthetic dataset",
                    "purely fictional",
                    "all names, projects, and details",
                )
            ):
                continue

            if cleaned not in facts:
                facts.append(cleaned)

        return facts

    @staticmethod
    def _format_source_citations(document_ids: List[str]) -> str:
        """Format unique document IDs as citations."""
        unique_ids = list(dict.fromkeys(document_ids))
        return " ".join(f"[{document_id}]" for document_id in unique_ids)

    async def generate_answer(
        self,
        question: str,
        sources: List[SearchResultItem],
    ) -> Tuple[str, str]:
        """Generate a cited response and disclose gaps in retrieved evidence."""
        if not sources:
            return (
                "Insufficient evidence: the accessible retrieved excerpts do "
                "not support an answer to this question.",
                "insufficient_evidence",
            )

        # Group evidence by heading. Multiple chunks can contribute to one answer.
        sections: dict[str, dict] = {}

        for item in sources:
            heading = (item.heading or "Retrieved excerpt").strip()
            document_id = item.document_id
            excerpt = self._clean_excerpt(item.excerpt)

            if not excerpt:
                continue

            if heading not in sections:
                sections[heading] = {
                    "document_id": document_id,
                    "facts": [],
                }

            facts = self._extract_facts(excerpt) or [excerpt]

            for fact in facts:
                if fact not in sections[heading]["facts"]:
                    sections[heading]["facts"].append(fact)

        if not sections:
            return (
                "Insufficient evidence: no usable facts were found in the "
                "retrieved excerpts.",
                "insufficient_evidence",
            )

        question_lower = question.lower()
        asks_for_milestones = any(
            term in question_lower
            for term in (
                "30-60-90",
                "30-day",
                "60-day",
                "90-day",
                "30 day",
                "60 day",
                "90 day",
                "31–60",
                "61–90",
                "success criteria",
                "success criterion",
            )
        )

        answer_lines: List[str] = []

        if asks_for_milestones:
            milestone_groups = [
                ("Days 1–30", ("30-day milestone", "week 1")),
                ("Days 31–60", ("60-day milestone",)),
                ("Days 61–90", ("90-day milestone",)),
            ]

            for period, prefixes in milestone_groups:
                matched_sections = [
                    (heading, section)
                    for heading, section in sections.items()
                    if any(
                        heading.lower().startswith(prefix)
                        for prefix in prefixes
                    )
                ]

                answer_lines.extend([f"## {period}", ""])

                if not matched_sections:
                    answer_lines.extend(
                        [
                            "- The corresponding milestone details were not "
                            "found in the retrieved excerpts.",
                            "",
                        ]
                    )
                    continue

                document_ids: List[str] = []

                for heading, section in matched_sections:
                    document_id = section["document_id"]

                    if document_id not in document_ids:
                        document_ids.append(document_id)

                    answer_lines.extend([f"### {heading}", ""])

                    for fact in section["facts"]:
                        answer_lines.append(f"- {fact}")

                    answer_lines.append("")

                citations = self._format_source_citations(document_ids)
                answer_lines.append(f"**Source:** {citations}")
                answer_lines.append("")

                answer_lines.append(
                    "**Success criteria:** The retrieved evidence describes "
                    "activities and deliverables but does not establish "
                    "separate measurable pass/fail criteria."
                )
                answer_lines.append("")

        else:
            answer_lines.extend(
                [
                    f'**Company Documentation Summary for:** '
                    f'"{question.strip()}"',
                    "",
                ]
            )

            for heading, section in sections.items():
                answer_lines.extend([f"### {heading}", ""])

                for fact in section["facts"]:
                    answer_lines.append(f"- {fact}")

                answer_lines.extend(
                    [
                        "",
                        f"**Source:** [{section['document_id']}]",
                        "",
                    ]
                )

        answer_lines.append(
            "> This answer is based on retrieved documentation. "
            "Details absent from the retrieved excerpts are not inferred."
        )

        return "\n".join(answer_lines), "grounded"
