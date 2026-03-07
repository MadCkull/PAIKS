# Google Drive AI Assistant (Django + Flask)

This project is a starting point for an app where users can connect their Google Drive and run AI-powered search over their documents.

- Django renders the web UI.
- A separate Flask service will host the API endpoints (Google Drive sync, embeddings, search, etc.).

## Prerequisites

- Python 3.10+ in your PATH
- `virtualenv` support (standard with Python 3)

## Setup

```bash
cd c:\\xampp\\htdocs\\PAIKS
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
```

## Running the Django app

```bash
cd c:\\xampp\\htdocs\\PAIKS
.venv\\Scripts\\python manage.py migrate
.venv\\Scripts\\python manage.py runserver 8000
```

Open `http://127.0.0.1:8000/` in your browser to see the UI.

## Running the Flask API

In a second terminal:

```bash
cd c:\\xampp\\htdocs\\PAIKS
.venv\\Scripts\\python flask_api.py
```

- Health check: `GET http://127.0.0.1:5001/health`
- Example search endpoint: `POST http://127.0.0.1:5001/search` with JSON body:

```json
{ "query": "example keyword" }
```

## Next steps

- Wire Google OAuth and Drive API into the Flask service.
- Implement document ingestion + vector search over the fetched files.
- Hook the Django UI to call the Flask `/search` endpoint via AJAX.

