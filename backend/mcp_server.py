from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from routes.pitch import (
    DEFAULT_DOCUMENT,
    DocumentStore,
    QuestionRequest,
    _answer_question_from_store,
)


class PitchAnswer(BaseModel):
    question: str
    answer: str
    grounded: bool
    source_refs: list[dict[str, str]]


server = MCPServer(
    "Pitchroom AI",
    instructions="Answer pitch questions only from the included synthetic demo brief. Cite matching source sections and say when the brief does not contain an answer.",
)
demo_store = DocumentStore(DEFAULT_DOCUMENT)


@server.tool(
    title="Ask the pitch",
    description="Answer a founder or judge question from Pitchroom's bundled demo brief, with source citations or an explicit not-found response.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    structured_output=True,
)
def ask_pitch(
    question: Annotated[
        str,
        Field(min_length=2, max_length=2000, description="A question about the pitch brief."),
    ],
) -> PitchAnswer:
    """Answer from the bundled, non-sensitive Pitchroom demo source only."""
    result = _answer_question_from_store(
        QuestionRequest(question=question), demo_store, allow_generation=False
    )
    return PitchAnswer(
        question=result["question"],
        answer=result["answer"],
        grounded=result["grounded"],
        source_refs=result["source_refs"],
    )
