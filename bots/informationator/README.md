# Informationator

RAG-powered Signal Q&A bot that answers questions from your document knowledge base.

Informationator ingests your documents (PDFs, Word files, PowerPoints, images, videos) and answers questions about them via Signal direct messages or @mentions in group chats.

## Features

- **RAG Pipeline**: Retrieval Augmented Generation using ChromaDB and Ollama
- **Multiple Document Formats**: PDF, Word (.docx), PowerPoint (.pptx), OpenDocument (.odt), text files
- **Vision Support**: Process images and videos using vision models
- **Auto-Ingestion**: File watcher automatically indexes new documents
- **Group Knowledge Bases**: Groups can upload documents via @mention + attachment
- **Source Citations**: Answers include references to source documents

## Architecture

```
Signal Message (DM or @mention)
    ↓
Q&A Handler
    ↓
RAG Pipeline:
  1. Embed question (nomic-embed-text)
  2. Search ChromaDB for relevant chunks
  3. Build context from top-k results
  4. Generate answer (dolphin-mistral)
    ↓
Formatted Response with Sources
```

## Commands

**In DMs** (no @mention needed):

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/status` | Knowledge base status |
| `/sources` | List indexed documents |

**In Groups** (@mention required):

| Command | Description |
|---------|-------------|
| `@bot /help` | Show available commands |
| `@bot /status` | Knowledge base status |
| `@bot /docs list` | List documents in group's KB |
| `@bot /docs delete <name>` | Delete a document from group's KB |

## Usage

### Direct Messages

```
You: What is the return policy?
Bot: 📖 Based on the documentation:
     The return policy allows returns within 30 days...

     📎 Sources:
     • return-policy.pdf (Page 2)
```

### Group @Mentions

```
@Informationator What are the system requirements?
```

### Group Document Uploads

Upload documents to a group's knowledge base:

```
@Informationator [attach PDF, DOCX, image, or video]
Bot: ✓ Added document.pdf to group knowledge base (12 chunks indexed)
```

## Supported File Types

**Documents:**
- PDF (`.pdf`)
- Microsoft Word (`.docx`)
- PowerPoint (`.pptx`)
- OpenDocument (`.odt`)
- Text files (`.txt`, `.md`, `.rst`, `.csv`, `.json`, `.yaml`)

**Images** (with vision model):
- PNG, JPG, JPEG, GIF, WebP, BMP

**Videos** (with vision model):
- MP4, WebM, MOV, AVI

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `dolphin-mistral:7b` | Model for Q&A generation |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Model for embeddings |
| `OLLAMA_VISION_MODEL` | `qwen2.5vl:7b` | Model for images/videos |
| `DOCUMENTS_FOLDER` | `/data/documents` | Folder to watch for documents |
| `CHUNK_SIZE` | `512` | Text chunk size in characters |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RETRIEVAL_TOP_K` | `5` | Number of chunks to retrieve |

## Group Knowledge Bases

Groups can build their own knowledge base by uploading documents via @mention + attachment.

**Search Priority:**
1. Group-specific documents (highest priority)
2. Default knowledge base (fallback)
3. Combined by relevance score

## Requirements

Requires Ollama with these models:

```bash
# Required
ollama pull dolphin-mistral:7b    # Q&A generation
ollama pull nomic-embed-text      # Embeddings

# Optional (for images/videos)
ollama pull qwen2.5vl:7b          # Vision model
```
