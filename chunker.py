from dataclasses import dataclass
from ast_parser import CodeEntity

@dataclass
class Chunk:
    id: str
    file_path: str
    name: str
    kind: str
    start_line: int
    end_line: int
    text: str
    code: str
    docstring: str | None
    parent_class: str | None
    calls: list[str]

    def to_metadata(self) -> dict:
        return {
            "file_path": self.file_path,
            "name": self.name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent_class": self.parent_class or "",
            # Chroma metadata must be scalar, so store calls as a comma-separated string
            "calls": ",".join(self.calls),
        }


def _build_embedding_text(entity: CodeEntity) -> str:
    parts = [f"File: {entity.file_path}", f"{entity.kind}: {entity.name}"]
    if entity.parent_class:
        parts.append(f"Class: {entity.parent_class}")
    if entity.docstring:
        parts.append(f"Docstring: {entity.docstring}")
    parts.append(entity.source)
    return "\n".join(parts)


def chunk_entities(entities: list[CodeEntity]) -> list[Chunk]:
    chunks = []
    for i, entity in enumerate(entities):
        chunk_id = f"{entity.file_path}::{entity.name}::{entity.start_line}::{i}"
        chunks.append(Chunk(
            id=chunk_id,
            file_path=entity.file_path,
            name=entity.name,
            kind=entity.kind,
            start_line=entity.start_line,
            end_line=entity.end_line,
            text=_build_embedding_text(entity),
            code=entity.source,
            docstring=entity.docstring,
            parent_class=entity.parent_class,
            calls=list(dict.fromkeys(entity.calls)),  # dedupe, keep order
        ))
    return chunks