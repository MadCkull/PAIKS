# PAIKS — Personal AI Knowledge System

PAIKS is a locally-hosted, high-performance AI document assistant built with **Django** and powered by **Ollama**. It transforms your Google Drive into a private AI-powered search environment, allowing you to index and query your documents with semantic intelligence.

> [!IMPORTANT]
> **Privacy First:** No cloud AI APIs are used. Your data, tokens, and embeddings stay entirely on your local machine.

---

## 🚀 Key Features

- **Unified Single-Server Architecture:** Powered by a modern, modular Django backend.
- **Glassmorphic Native UI:** Exceptional, premium aesthetics with high-performance micro-interactions.
- **Semantic RAG Search:** Context-aware answers grounded in your own documents using ChromaDB and local LLMs (Ollama).
- **Google Drive Integration:** Simple OAuth connection to sync documents from specific folders or your entire Drive.
- **Local File Uploads:** Supports direct imports of `.pdf`, `.docx`, `.txt`, `.md`, and `.csv`.
- **Intelligent Citations:** Source attribution for AI anwers with inline citations and relevance scores.

---

## 🛠️ Project Architecture

PAIKS has been modernized into a unified structure that eliminates legacy overhead:

```text
PAIKS/
├── core/                  # Django project configuration
├── api/                   # Modular REST API endpoints
│   ├── services/          # Core business logic (RAG pipeline, Drive sync, Auth)
│   └── views/             # Category-specific API handlers
├── assistant/             # Frontend application (UI & Templates)
│   ├── static/            # Modular JS/CSS architecture
│   └── templates/         # Component-based HTML structure
├── .storage/              # Internal data & config (not in Git)
│   ├── chroma_db/         # Local vector database
│   ├── local_files/       # Uploaded document repository
│   └── *.json             # Encrypted tokens and user preferences
└── launcher.py            # Unified system launcher
```

---

## 🏗️ Prerequisites

| Requirement | Purpose |
|---|---|
| **Python 3.13+** | The core application runtime |
| **Ollama** | Local LLM inference engine ([Download](https://ollama.com)) |
| **Google Account** | For document synchronization |

---

## 🚦 Quick Start

1. **Setup Your Environment:**
   ```powershell
   # Create and activate virtual environment
   python -m venv .venv
   .\.venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configure Google Cloud:**
   - Place your Google OAuth `credentials.json` in the root directory.
   - Set up your `.env` file based on the provided `.env.example`.

3. **Launch the Application:**
   ```powershell
   # Use the unified launcher
   .\run.bat
   ```
   *The app will automatically verify dependencies, clean up stale processes, and start the system at `http://localhost:8000`.*

---

## 📄 License & Use

PAIKS is designed for local, private research and knowledge management. All document processing happens on-device using ONNX-based embeddings and local LLM inference.
