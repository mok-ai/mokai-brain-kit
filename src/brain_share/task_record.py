from dataclasses import dataclass, field
from brain_share.wiki_page import WikiPage

VALID_STATUS = {"pending", "in_progress", "done", "blocked"}

@dataclass
class TaskRecord:
    task: str = ""
    status: str = "pending"
    outputs: list = field(default_factory=list)
    links: list = field(default_factory=list)
    lessons: str = ""
    division: str = ""
    sensitivity: str = "internal"
    updated: str = ""

def validate(rec: TaskRecord) -> None:
    if not rec.task:
        raise ValueError("task must be non-empty")
    if rec.status not in VALID_STATUS:
        raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")

def to_wiki_page(rec: TaskRecord) -> WikiPage:
    validate(rec)
    outs = "\n".join(f"- {o}" for o in rec.outputs) or "- (없음)"
    body = (f"# {rec.task}\n\n"
            f"- 상태: {rec.status}\n"
            f"## 산출물\n{outs}\n"
            f"## 교훈\n{rec.lessons or '(없음)'}\n")
    return WikiPage(
        topic="task_" + rec.task.replace(" ", "_")[:40], namespace=rec.division,
        sensitivity=rec.sensitivity, updated=rec.updated, sources=[],
        promote="pending", entities=list(rec.links), relations=[], body=body,
    )
