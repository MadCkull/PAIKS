<div align="center">
  <img src="https://img.shields.io/badge/PAIKS-Personal%20AI%20Knowledge%20System-6B46C1?style=for-the-badge" alt="PAIKS" />
  <h1>🚀 PAIKS Setup & Execution Guide</h1>
  <p><strong>The ultimate guide to configuring and running your completely private AI knowledge base.</strong></p>

  <img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows Support" />
  <img src="https://img.shields.io/badge/Python-3.13+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/Ollama-Local_LLM-black.svg?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama" />
</div>

<br>

<div style="background: rgba(107, 70, 193, 0.1); border: 2px solid #6B46C1; border-radius: 15px; padding: 20px; margin-bottom: 20px; text-align: center;">
  <h3 style="margin-top: 0; color: #6B46C1;">✨ Fully Automated Setup</h3>
  <p>The PAIKS unified launcher (<code>Launch-PAIKS.bat</code>) <strong>handles absolutely everything for you</strong>! It automatically creates the isolated virtual environment (<code>.venv</code>), and installs all required Python packages. You just need to run the launcher, sit back, and watch it do the work!</p>
</div>

---

## 📋 Prerequisites

Before we begin, please ensure your system has the following installed:

| Requirement      | Description                                                | Link                                                 |
| :--------------- | :--------------------------------------------------------- | :--------------------------------------------------- |
| **Python 3.13+** | Core runtime environment. Ensure `Add to PATH` is checked! | [Download Python](https://www.python.org/downloads/) |
| **Ollama**       | Local LLM engine required for processing and answering.    | [Download Ollama](https://ollama.com/)               |
| **Git**          | For version control and cloning the repository.            | [Download Git](https://git-scm.com/)                 |

> [!IMPORTANT]
> **Ollama Models:** Once Ollama is installed, you need to pull the default model. Open your terminal and run:
>
> ```powershell
> ollama run llama3.2
> ```
>
> _(Keep Ollama running in the background while using PAIKS)._

---

## 🛠️ Step 1: Clone & Initialize

Let's grab the code to your local machine.

**Clone the repository:**

```powershell
git clone https://github.com/MadCkull/PAIKS.git
cd PAIKS
```

_(The launcher will automatically create the virtual environment for you in Step 3!)_

---

## ⚙️ Step 2: Environment Configuration

PAIKS requires basic configuration to link up its core components.

**1. Prepare the Environment File:**
Duplicate the template file to create your active configuration.

```powershell
copy .env.example .env
```

Open `.env` and set `SECRET_KEY` to a random string, and ensure `DEFAULT_MODEL` is set to `llama3.2`.

**2. Google Drive Sync Configuration (Optional):**
If you plan to use Google Drive synchronization, you need to provide your Google Cloud OAuth credentials file.

> [!WARNING] You must save your downloaded Google credentials file exactly here:
> **`.storage/auth/google_creds.json`**

---

## 🚀 Step 3: Launching PAIKS

### 🌟 Method A: The Unified Launcher (Recommended)

The PAIKS system includes a smart, unified launcher that creates your environment, manages the database, cleans up stale background tasks, and **automatically installs all missing dependencies**!

Simply run:

```powershell
.\Launch-PAIKS.bat
```

_(Alternatively: `python launcher.py`)_

The smart launcher will pop up dashboard in your terminal, start the server, and give you live status updates!

### 🔧 Method B: Manual Startup (For Developers)

If you prefer running the raw Django server yourself without the rich dashboard and auto-installer:

```powershell
# 1. Install dependencies manually
pip install -r requirements.txt

# 2. Run the Django development server
python manage.py runserver
```

---

> [!NOTE]
> Once the server is running, open your web browser and navigate to:
> **[http://localhost:8000](http://localhost:8000)**

## 🛑 Stopping the Server

When you are finished using PAIKS, simply go to your terminal window and press `CTRL + C`.
The smart launcher will safely spin down the Django server, terminate background tasks, and save any pending caches.

---

<div align="center">
  <i>Enjoy your deeply integrated, private AI knowledge system! 🎉</i>
</div>
