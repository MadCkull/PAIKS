import json
2: import logging
3: import os
4: import pathlib
5: import time
6: from django.http import JsonResponse
7: 
8: from api.services.google_auth import get_creds
9: from api.services.google_drive import drive_service
10: from api.services.config import load_cache, load_app_settings, LOCAL_ALLOWED_EXTENSIONS
11: from api.views.drive import refresh_local_stats
12: 
13: # --- NEW RAG ARCHITECTURE IMPORTS ---
14: from api.services.rag.indexer import get_vector_store, CLOUD_COLLECTION, LOCAL_COLLECTION
15: from api.services.rag.ingestion.parsers import parse_cloud_file, parse_local_file
16: from api.services.rag.ingestion.chunking import chunk_documents
17: from api.services.rag.ingestion.pipeline import ingest_nodes_to_collection
18: from api.services.rag.retrieval.hybrid import get_base_retriever, get_hybrid_merging_retriever
19: from api.services.rag.retrieval.reranker import get_cross_encoder_reranker
20: from api.services.rag.generation.engine import build_query_engine, classify_intent, get_general_response
21: from api.services.rag.ingestion.embedder import get_embedder
22: 
23: from llama_index.core import VectorStoreIndex, QueryBundle
24: from llama_index.core.retrievers import BaseRetriever
25: 
26: logger = logging.getLogger(__name__)
27: 
28: _ingest_progress: dict = {"running": False, "processed": 0, "total": 0, "done": False, "error": None}
29: 
30: def status(request):
31:     """
32:     Returns the status of the Qdrant DB points.
33:     """
34:     try:
35:         from api.services.rag.indexer import get_qdrant_client
36:         client = get_qdrant_client()
37:         local_count = client.get_collection(LOCAL_COLLECTION).points_count if client.collection_exists(LOCAL_COLLECTION) else 0
38:         cloud_count = client.get_collection(CLOUD_COLLECTION).points_count if client.collection_exists(CLOUD_COLLECTION) else 0
39:         total_chunks = local_count + cloud_count
40:         return JsonResponse({
41:             "indexed": total_chunks > 0,
42:             "total_chunks": total_chunks,
43:             "ingest_running": _ingest_progress["running"],
44:             "ingest_progress": _ingest_progress,
45:         })
46:     except Exception as e:
47:         logger.warning(f"RAG status check failed: {e}")
48:         return JsonResponse({"indexed": False, "total_chunks": 0, "ingest_running": False})
49: 
50: 
51: def ingest(request):
52:     global _ingest_progress
53: 
54:     if _ingest_progress.get("running"):
55:         return JsonResponse({"error": "Ingest already running. Check /api/rag/status for progress."}, status=409)
56: 
57:     app_settings = load_app_settings()
58:     cloud_enabled = app_settings.get("cloud_enabled", True)
59:     local_enabled = app_settings.get("local_enabled", True)
60:     local_root = app_settings.get("local_root_path")
61: 
62:     cloud_docs = []
63:     local_docs = []
64: 
65:     # ── Gather Cloud Files ──────────────────────────────────
66:     if cloud_enabled:
67:         creds = get_creds()
68:         if creds:
69:              service = drive_service(creds)
70:              cache = load_cache()
71:              for f in cache.get("files", []):
72:                 cloud_docs.append({
73:                     "id": f.get("id"),
74:                     "name": f.get("name"),
75:                     "mime": f.get("mimeType"),
76:                     "link": f.get("webViewLink", ""),
77:                     "modified": f.get("modifiedTime", ""),
78:                 })
79: 
80:     # ── Gather Local Files ──────────────────────────────────
81:     if local_enabled and local_root and os.path.exists(local_root):
82:         for root, dirs, filenames in os.walk(local_root):
83:             for filename in filenames:
84:                 ext = pathlib.Path(filename).suffix.lower()
85:                 if ext in LOCAL_ALLOWED_EXTENSIONS:
86:                     full_path = os.path.join(root, filename)
87:                     local_docs.append({
88:                         "id": f"local__{full_path}",
89:                         "name": filename,
90:                         "local_path": full_path,
91:                         "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(full_path))),
92:                     })
93: 
94:     if not cloud_docs and not local_docs:
95:         return JsonResponse({"error": "No files found to process."}, status=400)
96: 
97:     total_files = len(cloud_docs) + len(local_docs)
98:     _ingest_progress = {"running": True, "processed": 0, "total": total_files, "done": False, "error": None}
99: 
100:     processed, skipped, total_chunks = 0, 0, 0
101:     errors = []
102: 
103:     # ── Process Cloud Collection ────────────────────────────
104:     if cloud_docs:
105:         service = drive_service(get_creds())
106:         parsed_docs = []
107:         for f in cloud_docs:
108:             doc = parse_cloud_file(service, f)
109:             if doc:
110:                 parsed_docs.append(doc)
111:             else:
112:                 skipped += 1
113:             processed += 1
114:             _ingest_progress["processed"] = processed
115: 
116:         if parsed_docs:
117:             try:
118:                 nodes = chunk_documents(parsed_docs)
119:                 total_chunks += len(nodes)
120:                 ingest_nodes_to_collection(nodes, CLOUD_COLLECTION)
121:             except Exception as e:
122:                 logger.error(f"Cloud ingestion failed: {e}")
123:                 errors.append(str(e))
124: 
125:     # ── Process Local Collection ────────────────────────────
126:     if local_docs:
127:         parsed_docs = []
128:         for f in local_docs:
129:             doc = parse_local_file(f)
130:             if doc:
131:                 parsed_docs.append(doc)
132:             else:
133:                 skipped += 1
134:             processed += 1
135:             _ingest_progress["processed"] = processed
136: 
137:         if parsed_docs:
138:             try:
139:                 nodes = chunk_documents(parsed_docs)
140:                 total_chunks += len(nodes)
141:                 ingest_nodes_to_collection(nodes, LOCAL_COLLECTION)
142:             except Exception as e:
143:                 logger.error(f"Local ingestion failed: {e}")
144:                 errors.append(str(e))
145: 
146:     _ingest_progress.update({"running": False, "done": True})
147: 
148:     try: refresh_local_stats()
149:     except Exception: pass
150: 
151:     return JsonResponse({
152:         "status": "ingested",
153:         "files_processed": processed - skipped,
154:         "files_skipped": skipped,
155:         "total_chunks": total_chunks,
156:         "errors": errors[:10],
157:     })
158: 
159: # --- Custom Multi-Collection Retriever ---
160: class MultiCollectionRetriever(BaseRetriever):
161:     def __init__(self, cloud_retriever, local_retriever):
162:         self.cloud_retriever = cloud_retriever
163:         self.local_retriever = local_retriever
164:         super().__init__()
165: 
166:     def _retrieve(self, query_bundle: QueryBundle):
167:         nodes = []
168:         if self.cloud_retriever:
169:             try: nodes.extend(self.cloud_retriever.retrieve(query_bundle))
170:             except Exception: pass
171:         if self.local_retriever:
172:             try: nodes.extend(self.local_retriever.retrieve(query_bundle))
173:             except Exception: pass
174:         return nodes
175: 
176: def search(request):
177:     try:
178:         payload = json.loads(request.body) if request.body else {}
179:     except ValueError:
180:         payload = {}
181:         
182:     query = payload.get("query", "").strip()
183:     if not query:
184:         return JsonResponse({"error": "query is required"}, status=400)
185: 
186:     app_settings = load_app_settings()
187:     cloud_enabled = app_settings.get("cloud_enabled", True)
188:     local_enabled = app_settings.get("local_enabled", True)
189: 
190:     # 1. Deterministic Intent Routing
191:     intent = classify_intent(query)
192:     logger.info(f"Classified intent: {intent} for query: {query}")
193: 
194:     if intent == "GENERAL":
195:         answer_str = get_general_response(query)
196:         return JsonResponse({
197:             "query": query,
198:             "answer": answer_str,
199:             "answer_model": "LlamaIndex Classifier (General)",
200:             "answer_error": None,
201:             "results": [],
202:             "total": 0,
203:             "source": "conversational",
204:             "indexed": True,
205:             "settings": app_settings,
206:         })
207: 
208:     # 2. RAG Pathway (SEARCH)
210:     try:
211:         cloud_retriever = None
212:         local_retriever = None
213:         
214:         # Build individual hybrid retrievers if collections exist
215:         from api.services.rag.indexer import get_qdrant_client
216:         
217:         client = get_qdrant_client()
218:         embedder = get_embedder()
219: 
220:         if cloud_enabled and client.collection_exists(CLOUD_COLLECTION):
221:             idx = VectorStoreIndex.from_vector_store(get_vector_store(CLOUD_COLLECTION), embed_model=embedder)
222:             base_ret = get_base_retriever(idx, top_k=20)
223:             cloud_retriever = base_ret
224: 
225:         if local_enabled and client.collection_exists(LOCAL_COLLECTION):
226:             idx = VectorStoreIndex.from_vector_store(get_vector_store(LOCAL_COLLECTION), embed_model=embedder)
227:             base_ret = get_base_retriever(idx, top_k=20)
228:             local_retriever = base_ret
229: 
230:         multi_retriever = MultiCollectionRetriever(cloud_retriever, local_retriever)
231:         reranker = get_cross_encoder_reranker(top_n=5)
232:         
233:         engine = build_query_engine(multi_retriever, reranker)
234:         
235:         logger.info(f"Querying RAG engine: {query}")
236:         response = engine.query(query)
237:         
238:         # Parse Source Nodes for frontend
239:         hits = []
240:         seen_fids = set()
241:         
242:         for node in response.source_nodes:
243:             meta = node.node.metadata
244:             fid = meta.get("file_id") or meta.get("file_name", "unknown")
245:             if fid not in seen_fids:
246:                 seen_fids.add(fid)
247:                 score = round(node.score if node.score else 0.0, 3)
248:                 source_type = meta.get("source", "google")
249:                 hits.append({
250:                     "id": fid,
251:                     "name": meta.get("file_name", "Unknown"),
252:                     "mimeType": meta.get("mime_type", ""),
253:                     "webViewLink": meta.get("web_view_link", ""),
254:                     "modifiedTime": meta.get("modified_time", ""),
255:                     "snippet": node.node.get_content()[:320].strip(),
256:                     "score": score,
257:                     "source": source_type,
258:                     "localPath": meta.get("local_path", ""),
259:                     "relevance_hint": f"{'Cloud Match' if source_type == 'cloud' else 'Local Match'} · Reranked Score: {score}",
260:                 })
261: 
262:         answer_str = str(response).strip()
263:         if not answer_str or answer_str == "None":
264:             answer_str = "I could not find relevant information regarding this in the indexed files."
265: 
266:         return JsonResponse({
267:             "query": query,
268:             "answer": answer_str,
269:             "answer_model": "LlamaIndex Engine",
270:             "answer_error": None,
271:             "results": hits,
272:             "total": len(hits),
273:             "source": "semantic_multi",
274:             "indexed": True,
275:             "settings": app_settings,
276:         })
277:         
278:     except Exception as exc:
279:         import traceback
280:         logger.error("New LlamaIndex Search error: %s\n%s", exc, traceback.format_exc())
281:         return JsonResponse({
282:             "query": query,
283:             "answer": None,
284:             "answer_error": f"LlamaIndex engine failed: {exc}",
285:             "answer_model": None,
286:             "results": [],
287:             "total": 0,
288:             "source": "error",
289:             "indexed": True,
290:             "settings": app_settings,
291:         })
292: 
293: # LLM Status endpoint remains the same since it's just Ollama generic checks
294: def llm_status(request):
295:     try:
296:         from api.services.llm_client import ollama_list_models
297:         from api.services.config import load_llm_config
298:         cfg = load_llm_config()
299:         models = ollama_list_models(cfg.get("base_url", "http://localhost:11434"))
300:         return JsonResponse({
301:             "reachable": True,
302:             "provider": cfg.get("provider", "ollama"),
303:             "current_model": cfg.get("model", ""),
304:             "base_url": cfg.get("base_url", ""),
305:             "available_models": models
306:         })
307:     except Exception:
308:         return JsonResponse({"reachable": False})
309: 
310: def save_llm_config(request):
311:     try:
312:         payload = json.loads(request.body)
313:         from api.services.config import load_llm_config, save_llm_config as save_cfg
314:         cfg = load_llm_config()
315:         if "base_url" in payload: cfg["base_url"] = payload["base_url"]
316:         if "model" in payload: cfg["model"] = payload["model"]
317:         if "provider" in payload: cfg["provider"] = payload["provider"]
318:         save_cfg(cfg)
319:         return JsonResponse({"status": "saved"})
320:     except Exception as e:
321:         return JsonResponse({"error": str(e)}, status=400)
