"""Text chunking for RAG."""

from dataclasses import dataclass
from typing import List, Optional

from signalinator_core import get_logger

logger = get_logger(__name__)


@dataclass
class Chunk:
    """A text chunk with metadata."""

    text: str
    chunk_index: int
    document_id: str
    filename: str
    page_reference: Optional[str] = None
    start_char: int = 0
    end_char: int = 0


class TextChunker:
    """Recursive text chunking with configurable size and overlap."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Splitting hierarchy
        self.separators = [
            "\n\n",  # Paragraphs
            "\n",    # Lines
            ". ",    # Sentences
            ", ",    # Clauses
            " ",     # Words
            "",      # Characters (last resort)
        ]

    def chunk_text(
        self,
        text: str,
        document_id: str,
        filename: str,
    ) -> List[Chunk]:
        """Split text into overlapping chunks."""
        if not text or not text.strip():
            return []

        # Clean and normalize
        text = text.replace("\r\n", "\n")

        # Extract page references
        page_map = self._build_page_map(text)

        # Recursive splitting
        raw_chunks = self._split_recursive(text, self.separators)

        # Build chunks with overlap
        chunks = []
        char_pos = 0

        for i, chunk_text in enumerate(raw_chunks):
            if not chunk_text.strip():
                char_pos += len(chunk_text)
                continue

            # Find page reference
            page_ref = self._get_page_reference(char_pos, page_map)

            chunk = Chunk(
                text=chunk_text.strip(),
                chunk_index=len(chunks),
                document_id=document_id,
                filename=filename,
                page_reference=page_ref,
                start_char=char_pos,
                end_char=char_pos + len(chunk_text),
            )
            chunks.append(chunk)
            char_pos += len(chunk_text)

        logger.debug(f"Created {len(chunks)} chunks from {filename}")
        return chunks

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using separator hierarchy."""
        if len(text) <= self.chunk_size:
            return [text]

        # Find best separator
        separator = separators[0] if separators else ""
        remaining_seps = separators[1:] if len(separators) > 1 else [""]

        # Split on separator
        if separator:
            parts = text.split(separator)
        else:
            # Character-level split as last resort
            return [text[i:i + self.chunk_size]
                    for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        # Merge small parts, split large parts
        result = []
        current = ""

        for part in parts:
            if not part:
                continue

            # Would adding this part exceed chunk size?
            combined = current + separator + part if current else part

            if len(combined) <= self.chunk_size:
                current = combined
            else:
                # Save current chunk
                if current:
                    result.append(current)

                # Handle oversized part
                if len(part) > self.chunk_size:
                    # Recursively split with next separator
                    sub_chunks = self._split_recursive(part, remaining_seps)
                    result.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current:
            result.append(current)

        return result

    def _build_page_map(self, text: str) -> List[tuple]:
        """Build map of character positions to page references."""
        import re

        page_map = []
        pattern = r'\[(?:Page|Slide)\s+(\d+)\]'

        for match in re.finditer(pattern, text):
            page_map.append((match.start(), match.group(0)))

        return page_map

    def _get_page_reference(self, char_pos: int, page_map: List[tuple]) -> Optional[str]:
        """Get page reference for a character position."""
        if not page_map:
            return None

        # Find the most recent page marker before this position
        current_ref = None
        for pos, ref in page_map:
            if pos <= char_pos:
                current_ref = ref
            else:
                break

        return current_ref
