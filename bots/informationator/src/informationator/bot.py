"""Informationator bot implementation."""

import os
import time
from typing import Dict, Optional, Callable

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)

from .database import InformationatorRepository
from .rag import (
    DocumentLoader,
    TextChunker,
    OllamaEmbeddings,
    ChromaVectorStore,
    DocumentRetriever,
    QAEngine,
    IngestionManager,
)

logger = get_logger(__name__)


class InformationatorBot(SignalinatorBot):
    """Informationator - RAG-based document Q&A bot.

    Ask questions about documents in your knowledge base.
    Upload documents via attachment + @mention.

    Commands:
    - /ask <question>: Ask a question
    - /docs list: List indexed documents
    - /docs delete <id>: Delete a document
    - /kb-status: Show knowledge base stats
    - /status: Show bot status
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
        ollama_host: str = None,
        ollama_model: str = None,
        ollama_embed_model: str = None,
        chromadb_path: str = None,
        documents_folder: str = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        retrieval_top_k: int = 5,
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = InformationatorRepository(engine)

        # RAG configuration
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "dolphin-mistral:7b")
        self.ollama_embed_model = ollama_embed_model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.chromadb_path = chromadb_path or os.getenv("CHROMADB_PATH", "/data/chromadb")
        self.documents_folder = documents_folder or os.getenv("DOCUMENTS_FOLDER", "/documents")

        # Initialize RAG components
        self.loader = DocumentLoader()
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embeddings = OllamaEmbeddings(
            host=self.ollama_host,
            model=self.ollama_embed_model,
        )
        self.vector_store = ChromaVectorStore(persist_directory=self.chromadb_path)
        self.retriever = DocumentRetriever(
            embeddings=self.embeddings,
            vector_store=self.vector_store,
            top_k=retrieval_top_k,
        )
        self.qa_engine = QAEngine(
            retriever=self.retriever,
            ollama_host=self.ollama_host,
            ollama_model=self.ollama_model,
        )
        self.ingestion = IngestionManager(
            loader=self.loader,
            chunker=self.chunker,
            embeddings=self.embeddings,
            vector_store=self.vector_store,
        )

    @property
    def bot_name(self) -> str:
        return "Informationator"

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/ask": BotCommand(
                name="/ask",
                description="Ask a question about documents",
                handler=self._handle_ask,
                usage="/ask <question>",
            ),
            "/docs": BotCommand(
                name="/docs",
                description="Manage documents",
                handler=self._handle_docs,
                usage="/docs list | /docs delete <id>",
            ),
            "/kb-status": BotCommand(
                name="/kb-status",
                description="Show knowledge base statistics",
                handler=self._handle_kb_status,
            ),
            "/status": BotCommand(
                name="/status",
                description="Show bot status",
                handler=self._handle_status,
            ),
            "/ingest": BotCommand(
                name="/ingest",
                description="Trigger document ingestion",
                handler=self._handle_ingest,
                admin_only=True,
            ),
        }

    def on_startup(self) -> None:
        """Initialize and ingest documents."""
        # Check Ollama availability
        if self.qa_engine.is_available():
            logger.info(f"Ollama connected: {self.ollama_model}")
        else:
            logger.warning("Ollama not available - Q&A will fail")

        # Initial document ingestion
        if os.path.exists(self.documents_folder):
            results = self.ingestion.ingest_folder(self.documents_folder)
            success = sum(1 for r in results if r.success)
            logger.info(f"Initial ingestion: {success}/{len(results)} documents")

        # Log KB stats
        chunk_count = self.vector_store.count()
        logger.info(f"Knowledge base: {chunk_count} chunks")

    def on_shutdown(self) -> None:
        pass

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        self.repo.create_or_update_group(group_id, group_name)
        return (
            "Hi! I'm Informationator. Ask me questions about documents!\n\n"
            "Just @mention me with your question, or use /ask <question>.\n"
            "Upload documents by sending them with an @mention."
        )

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle @mention questions in groups."""
        if not context.message:
            return None

        # Check for attachments (document upload)
        if context.attachments:
            return self._handle_attachment(context)

        # Treat the message as a question
        question = context.message.strip()
        if not question:
            return "Ask me a question about the documents!"

        return self._answer_question(question, context.group_id)

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle DM questions."""
        if not context.message:
            return None

        message = context.message.strip()

        # Check for commands
        if message.startswith("/"):
            return None  # Let command router handle it

        # Treat as question
        return self._answer_question(message, group_id=None)

    def _answer_question(self, question: str, group_id: str = None) -> str:
        """Answer a question using RAG."""
        if not question:
            return "Please provide a question."

        start_time = time.time()

        try:
            response = self.qa_engine.answer(question, group_id)
            response_time = int((time.time() - start_time) * 1000)

            # Record query for analytics
            self.repo.record_query(
                source_type="mention" if group_id else "dm",
                source_id=group_id or "dm",
                question_length=len(question),
                answer_length=len(response.answer),
                sources_count=len(response.sources),
                had_results=response.has_answer,
                response_time_ms=response_time,
            )

            return response.formatted_answer

        except Exception as e:
            logger.error(f"Error answering question: {e}")
            return f"Error processing question: {e}"

    def _handle_attachment(self, context: MessageContext) -> str:
        """Handle document attachment upload."""
        if not context.attachments:
            return "No attachment found."

        # Signal-cli stores attachments in /signal-cli-config/attachments/
        # We mount this as /signal-attachments in the bot container
        attachments_dir = os.getenv("SIGNAL_ATTACHMENTS_DIR", "/signal-attachments")

        results = []
        for attachment in context.attachments:
            filename = attachment.get("filename", "document")
            # signal-cli uses 'id' for the stored filename
            attachment_id = attachment.get("id")

            if not attachment_id:
                results.append(f"Could not access {filename}: no attachment id")
                continue

            file_path = os.path.join(attachments_dir, attachment_id)

            if not os.path.exists(file_path):
                logger.warning(f"Attachment not found at {file_path}")
                results.append(f"Could not access {filename}")
                continue

            if not DocumentLoader.is_supported(file_path):
                results.append(f"Unsupported file type: {filename}")
                continue

            # Ingest the document
            result = self.ingestion.ingest_file(file_path, group_id=context.group_id)

            if result.success:
                # Track in database
                doc = self.repo.create_document(
                    filename=result.filename,
                    file_path=file_path,
                    document_type=os.path.splitext(filename)[1][1:],
                    group_id=context.group_id,
                )
                self.repo.update_document_status(
                    doc_id=doc.id,
                    status="indexed",
                    chunk_count=result.chunk_count,
                    processing_time=result.processing_time,
                )
                results.append(f"Indexed {filename} ({result.chunk_count} chunks)")
            else:
                results.append(f"Failed to index {filename}: {result.error}")

        return "\n".join(results)

    # ==================== Command Handlers ====================

    def _handle_ask(self, context: CommandContext) -> str:
        """Handle /ask command."""
        question = context.args.strip()
        if not question:
            return "Usage: /ask <question>"

        return self._answer_question(question, context.message.group_id)

    def _handle_docs(self, context: CommandContext) -> str:
        """Handle /docs command."""
        args = context.args.strip().split(maxsplit=1)
        if not args:
            return "Usage: /docs list | /docs delete <filename>"

        action = args[0].lower()

        if action == "list":
            docs = self.repo.get_documents(
                group_id=context.message.group_id,
                status="indexed",
            )
            if not docs:
                return "No documents indexed for this group."

            lines = ["Indexed Documents:"]
            for doc in docs:
                lines.append(f"  [{doc.id}] {doc.filename} ({doc.chunk_count} chunks)")
            return "\n".join(lines)

        elif action == "delete":
            if len(args) < 2:
                return "Usage: /docs delete <document_id>"

            try:
                doc_id = int(args[1])
            except ValueError:
                return "Invalid document ID."

            doc = self.repo.get_document(doc_id)
            if not doc:
                return "Document not found."

            # Remove from vector store and database
            document_id = self.ingestion._generate_document_id(doc.file_path or doc.filename)
            self.ingestion.remove_document(document_id)
            self.repo.delete_document(doc_id)

            return f"Deleted: {doc.filename}"

        return "Usage: /docs list | /docs delete <id>"

    def _handle_kb_status(self, context: CommandContext) -> str:
        """Handle /kb-status command."""
        total_chunks = self.vector_store.count()
        group_chunks = 0
        if context.message.group_id:
            group_chunks = self.vector_store.count(context.message.group_id)

        doc_count = self.repo.get_document_count()
        stats = self.repo.get_query_stats(days=7)

        lines = [
            "Knowledge Base Status:",
            f"  Total chunks: {total_chunks}",
            f"  Group chunks: {group_chunks}",
            f"  Documents: {doc_count}",
            "",
            f"Query Stats (7 days):",
            f"  Total queries: {stats['total_queries']}",
            f"  Avg response time: {stats['avg_response_time_ms']}ms",
            f"  Success rate: {stats['success_rate']:.1f}%",
        ]
        return "\n".join(lines)

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command."""
        ollama_status = "connected" if self.qa_engine.is_available() else "unavailable"
        embed_status = "connected" if self.embeddings.is_available() else "unavailable"

        return (
            f"Informationator Status\n"
            f"  Ollama Q&A: {ollama_status}\n"
            f"  Ollama Embed: {embed_status}\n"
            f"  Model: {self.ollama_model}\n"
            f"  Embed Model: {self.ollama_embed_model}"
        )

    def _handle_ingest(self, context: CommandContext) -> str:
        """Handle /ingest command."""
        if not os.path.exists(self.documents_folder):
            return f"Documents folder not found: {self.documents_folder}"

        results = self.ingestion.ingest_folder(self.documents_folder)
        success = sum(1 for r in results if r.success)
        chunks = sum(r.chunk_count for r in results)

        return f"Ingested {success}/{len(results)} documents ({chunks} chunks)"
