"""CLI commands for Informationator."""

import os
import click

from signalinator_core import setup_logging, get_logger
from signalinator_core.signal import SignalCLI, SetupWizard

from ..bot import InformationatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Informationator - RAG-based document Q&A bot."""
    ctx.ensure_object(dict)
    setup_logging()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
@click.option('--voice', is_flag=True)
def setup(phone, config_dir, voice):
    """Set up Signal-CLI registration."""
    wizard = SetupWizard(phone, config_dir)
    if wizard.run_setup(use_voice=voice):
        click.echo("Setup completed!")
    else:
        click.echo("Setup failed.")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
def status(phone, config_dir):
    """Check Signal-CLI status."""
    wizard = SetupWizard(phone, config_dir)
    wizard.display_status()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
@click.option('--name', default='informationator')
def link(phone, config_dir, name):
    """Link as secondary device."""
    signal_cli = SignalCLI(phone, config_dir)
    try:
        linking_uri = signal_cli.link_device(name)
        click.echo(f"\nLinking URI:\n{linking_uri}\n")
        click.echo("Scan with Signal app: Settings > Linked Devices > +")
    except Exception as e:
        click.echo(f"Linking failed: {e}")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--db-path', envvar='DB_PATH', default='/data/informationator.db')
@click.option('--auto-accept-invites/--no-auto-accept-invites', envvar='AUTO_ACCEPT_GROUP_INVITES', default=True)
@click.option('--chunk-size', envvar='CHUNK_SIZE', default=512, type=int)
@click.option('--chunk-overlap', envvar='CHUNK_OVERLAP', default=50, type=int)
@click.option('--top-k', envvar='RETRIEVAL_TOP_K', default=5, type=int)
def daemon(phone, db_path, auto_accept_invites, chunk_size, chunk_overlap, top_k):
    """Run Informationator daemon."""
    click.echo("Starting Informationator daemon...")

    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "dolphin-mistral:7b")
    ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    chromadb_path = os.getenv("CHROMADB_PATH", "/data/chromadb")
    documents_folder = os.getenv("DOCUMENTS_FOLDER", "/documents")

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")
    click.echo(f"  Ollama: {ollama_host}")
    click.echo(f"  Q&A Model: {ollama_model}")
    click.echo(f"  Embed Model: {ollama_embed_model}")
    click.echo(f"  ChromaDB: {chromadb_path}")
    click.echo(f"  Documents: {documents_folder}")
    click.echo(f"  Chunk Size: {chunk_size}, Overlap: {chunk_overlap}")

    try:
        bot = InformationatorBot(
            phone_number=phone,
            db_path=db_path,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
            ollama_embed_model=ollama_embed_model,
            chromadb_path=chromadb_path,
            documents_folder=documents_folder,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            retrieval_top_k=top_k,
        )

        click.echo("\nInformationator initialized")
        click.echo("Commands: /help, /ask, /docs, /kb-status")
        click.echo("Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\nInformationator stopped.")
    except Exception as e:
        click.echo(f"\nError: {e}")
        logger.exception("Daemon error")
        exit(1)


@cli.command()
@click.option('--documents-folder', envvar='DOCUMENTS_FOLDER', default='/documents')
@click.option('--chromadb-path', envvar='CHROMADB_PATH', default='/data/chromadb')
@click.option('--chunk-size', envvar='CHUNK_SIZE', default=512, type=int)
@click.option('--chunk-overlap', envvar='CHUNK_OVERLAP', default=50, type=int)
def ingest(documents_folder, chromadb_path, chunk_size, chunk_overlap):
    """Manually ingest documents."""
    from ..rag import (
        DocumentLoader,
        TextChunker,
        OllamaEmbeddings,
        ChromaVectorStore,
        IngestionManager,
    )

    click.echo(f"Ingesting documents from {documents_folder}...")

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    loader = DocumentLoader()
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embeddings = OllamaEmbeddings(host=ollama_host, model=ollama_embed_model)
    vector_store = ChromaVectorStore(persist_directory=chromadb_path)
    ingestion = IngestionManager(loader, chunker, embeddings, vector_store)

    def progress(msg):
        click.echo(f"  {msg}")

    results = ingestion.ingest_folder(documents_folder, progress_callback=progress)

    success = sum(1 for r in results if r.success)
    chunks = sum(r.chunk_count for r in results)
    click.echo(f"\nIngested {success}/{len(results)} documents ({chunks} chunks)")


@cli.command("kb-status")
@click.option('--chromadb-path', envvar='CHROMADB_PATH', default='/data/chromadb')
def kb_status(chromadb_path):
    """Show knowledge base statistics."""
    from ..rag import ChromaVectorStore

    vector_store = ChromaVectorStore(persist_directory=chromadb_path)
    count = vector_store.count()
    click.echo(f"Knowledge Base: {count} chunks")


@cli.command()
@click.argument('question')
@click.option('--chromadb-path', envvar='CHROMADB_PATH', default='/data/chromadb')
@click.option('--top-k', envvar='RETRIEVAL_TOP_K', default=5, type=int)
def ask(question, chromadb_path, top_k):
    """Ask a question from the CLI."""
    from ..rag import (
        OllamaEmbeddings,
        ChromaVectorStore,
        DocumentRetriever,
        QAEngine,
    )

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "dolphin-mistral:7b")
    ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    embeddings = OllamaEmbeddings(host=ollama_host, model=ollama_embed_model)
    vector_store = ChromaVectorStore(persist_directory=chromadb_path)
    retriever = DocumentRetriever(embeddings, vector_store, top_k=top_k)
    qa_engine = QAEngine(retriever, ollama_host, ollama_model)

    click.echo(f"Question: {question}\n")

    response = qa_engine.answer(question)
    click.echo(response.formatted_answer)


if __name__ == "__main__":
    cli()
