# CodeSloth 🦥
**Understand the codebase. Skip the codebase safari.**

CodeSloth is a local-first codebase explorer. Paste a public GitHub URL to build a searchable file tree, a local-import dependency graph, and an optional Ollama-powered codebase guide.

## Requirements
- Python 3.10+
- Node.js 20+
- Git
- Optional: Ollama + a local coding model, e.g. `qwen2.5-coder:7b`

## Start the backend
From this directory:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
API docs: http://127.0.0.1:8000/docs

## Start the frontend
In another terminal:
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```
Open http://localhost:3000.

## Optional local AI
```bash
ollama pull qwen2.5-coder:7b
```
Ensure Ollama is running. Set `OLLAMA_MODEL` in `backend/.env` to the model you pulled. Without Ollama, indexing and dependency graphs still work; Q&A returns a deterministic index fallback.

## Demo
Try a public repo URL, for example `https://github.com/tiangolo/fastapi`. Start with a smaller repo for faster indexing.

## What it does
- Validates public GitHub URLs and shallow-clones repositories.
- Skips generated/vendor folders and large/binary files.
- Extracts imports and common function/class declarations with lightweight heuristics.
- Builds a file tree and graph of resolvable local imports.
- Stores analysis metadata and bounded source snippets in local SQLite for follow-up.
- Grounds Q&A in selected file excerpts; Ollama is optional.

## Limitations and safety
- Public GitHub repositories only; no private repository credentials.
- Repository source is not executed and dependencies are not installed.
- Import and symbol extraction are heuristics, not a compiler or complete call graph. Dynamic imports, aliases, reflection, generated code, and runtime dispatch may be missed.
- AI output can be wrong; verify against source.
- The backend stores extracted snippets locally in SQLite. Repository clone workspace is temporary. Do not use this on sensitive code unless you have reviewed the local data handling.
- Keep the backend bound to localhost. Do not expose it publicly without authentication, rate limiting, sandboxing, and resource limits.

## API
- `GET /health`
- `GET /api/ai/status`
- `POST /api/analyze` with `{"repo_url":"https://github.com/owner/repo"}`
- `POST /api/ask` with `{"analysis_id":"...","question":"Where is authentication handled?"}`
- `GET /api/analysis/{id}/file?path=...`

## Roadmap
Tree-sitter parsing, local-folder ingestion, secure private repo support, incremental indexing, stronger call graph tracing, graph export.
