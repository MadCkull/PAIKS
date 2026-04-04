<div align="center">
  <h1>🧠 PAIKS</h1>
  <p><strong>Personal AI Knowledge System</strong></p>
  <p>A high-performance, locally-hosted AI document assistant built with Django and powered by Ollama.</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.13+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
    <img src="https://img.shields.io/badge/Django-5.0+-092E20.svg?style=for-the-badge&logo=django&logoColor=white" alt="Django" />
    <img src="https://img.shields.io/badge/AI-Ollama-white.svg?style=for-the-badge&logo=ollama&logoColor=black" alt="Ollama" />
    <img src="https://img.shields.io/badge/Privacy-Local_First-success.svg?style=for-the-badge&logo=shield&logoColor=white" alt="Privacy First" />
  </p>
</div>

---

## 🌟 Overview

**PAIKS** transforms your unstructured documents and Google Drive into a private, AI-powered knowledge base. By utilizing local LLMs and vector embeddings, PAIKS provides semantic intelligence, context-aware answers, and robust RAG capabilities—all while keeping your data 100% private.

> [!IMPORTANT]  
> **Privacy First:** No cloud AI APIs are used. Your data, tokens, and embeddings stay entirely on your local machine.

---

## ✨ Key Features

### 🏢 Core Architecture
- **Unified Django Backend:** A modern, modular, single-server architecture eliminating legacy overhead.
- **Glassmorphic UI:** A premium, responsive interface featuring dynamic micro-interactions, full-screen modals, and an expandable navigation bar.
- **Project Knowledge Base:** Built-in self-awareness giving the LLM comprehensive context regarding the project's own structure and technical specifications.

### 🔌 Connectivity & Offline-First
- **"Use Locally" Mode:** Fully functional offline-first resilience. Bypass cloud authentication entirely and work exclusively with local files.
- **Google Drive Integration:** Seamless OAuth connection to sync documents from specific folders or your entire Drive when online.
- **Local File Uploads:** Supports direct imports of `.pdf`, `.docx`, `.txt`, `.md`, and `.csv`.

### 🧠 AI & Intelligence
- **Semantic RAG Search:** Grounded extraction using ChromaDB and local LLMs via Ollama.
- **Dynamic Chat Interface:** Context-aware interactions, intelligent resizing, and robust state management.
- **Intelligent Citations:** Source attribution for AI answers with inline citations, relevance scores, and a slide-out reference panel.

---

## 🛠️ Project Structure

PAIKS is organized into a clean, maintainable structure:

```text
PAIKS/
├── core/                  # Django project configuration & settings
├── api/                   # Modular REST API endpoints
│   ├── services/          # Core logic (RAG pipeline, Drive sync, Auth)
│   └── views/             # Category-specific API handlers
├── assistant/             # Frontend application (UI & Templates)
│   ├── static/            # Modular JS/CSS (Glassmorphism, animations)
│   └── templates/         # Component-based HTML structure
├── .storage/              # Internal data & config (Ignored in Git)
│   ├── chroma_db/         # Local vector database
│   ├── local_files/       # Uploaded document repository
│   └── *.json             # User preferences and encrypted tokens
├── launcher.py            # Unified system launcher
└── run.bat                # Windows quick-start script
```

---

## 🚀 Getting Started

### Prerequisites

| Requirement | Purpose |
|---|---|
| **[Python 3.13+](https://www.python.org/downloads/)** | The core application runtime |
| **[Ollama](https://ollama.com)** | Local LLM inference engine |
| **Google Account** *(Optional)* | For document synchronization via Google Drive |

### Installation

1. **Clone the Repository:**
   ```powershell
   git clone https://github.com/MadCkull/PAIKS.git
   cd PAIKS
   ```

2. **Setup Your Environment:**
   ```powershell
   # Create and activate virtual environment
   python -m venv .venv
   .\.venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Configure Settings:**
   - Copy the `.env.example` file to create a new `.env` file and adjust settings as needed.
   - *(Optional)* Place your Google OAuth `credentials.json` in the root directory for Drive sync.

4. **Launch the Application:**
   ```powershell
   # Use the unified launcher
   .\run.bat
   ```
   *The application will automatically verify dependencies, initialize the database (if needed), clean up stale processes, and start the system at `http://localhost:8000`.*

---

## 📖 Usage Modes

- **Offline-First (Local Mode):** Run PAIKS without internet access. Upload files directly to the local system and query them instantly using your local Ollama models.
- **Cloud-Synced Mode:** Connect your Google Drive to continuously index and semantically search your cloud documents.

---

## 🛡️ License & Privacy

PAIKS is designed for local, private research and knowledge management. All document processing happens on-device using local embeddings and local LLM inference. No data is transmitted to third-party AI services.
