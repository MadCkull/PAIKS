from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "flask-api"})


@app.post("/search")
def search_documents():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    results = [
        {
            "id": "example-doc-1",
            "title": "Sample Google Drive Document",
            "snippet": f"Matched snippet for: {query}",
        }
    ]
    return jsonify({"query": query, "results": results})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)

