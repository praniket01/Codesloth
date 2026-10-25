# CodeSloth 🦥

> **Meet your codebase without the awkward small talk.**

CodeSloth is a local-first codebase explorer that helps developers get oriented in an unfamiliar repository. Enter a public GitHub repository URL to explore its structure, inspect source files, visualize local dependencies, understand inferred architecture layers, and ask questions about the code with an optional local Ollama model.

## Why CodeSloth?

Starting in an unfamiliar codebase can mean hours of searching through folders and tracing imports. CodeSloth brings the first steps of codebase discovery into one workspace:

- **Explore the project tree** and inspect indexed files, imports, and detected symbols.
- **Visualize dependencies** with an interactive graph of detected local-import relationships.
- **Understand architecture** with a block diagram that groups files into inferred system layers and connects detected or inferred flows.
- **Ask CodeSloth** questions about the repository using relevant indexed source excerpts and an optional local Ollama model.
- **Keep analysis local**: the backend runs on your machine, and Ollama can generate answers without a hosted model API.

## Features

### Project tree and file inspector
Browse the repository structure and open files to inspect source excerpts, imports, and heuristically detected classes or functions.

### Dependency graph
Explore relationships between files when local imports can be resolved. Pan, zoom, search, and select graph nodes to inspect the corresponding file.

### Architecture flow
See a higher-level diagram built from source paths, imports, routes, and configuration patterns. Architecture blocks can represent areas such as frontend UI, API clients, backend routes/services, data access, infrastructure, tests, and external integrations when the analyzer can identify them.

> Architecture flow is a static-analysis aid, not a verified runtime trace. Connections may be inferred, and some real connections may not be detected.

### Local AI Q&A (optional)
Ask questions about where features live or how parts of the codebase relate. CodeSloth uses indexed excerpts as context and can call a local Ollama model. Without a reachable configured model, repository indexing and graph views remain available, while Q&A may return an index-based fallback.

## Tech stack

- **Frontend:** Next.js 15, React 19, TypeScript, `@xyflow/react`, Lucide
- **Backend:** Python, FastAPI, Uvicorn
- **Local AI:** Ollama (optional; for example, `qwen2.5-coder:7b` or another model configured in `.env`)
- **Persistence:** SQLite for local analysis metadata and extracted snippets
- **Repository retrieval:** Git shallow clone

## Requirements

- Python 3.10 or newer
- Node.js 20 or newer
- Git installed and available on your `PATH`
- Optional: [Ollama](https://ollama.com/) and a model that fits your machine

## Quick start

Run the backend and frontend in separate terminals.

### 1. Clone the project

```bash
git clone https://github.com/<YOUR_GITHUB_USERNAME>/codesloth.git
cd codesloth
```

Replace `<YOUR_GITHUB_USERNAME>` with your GitHub username or organization. If you choose a different repository name, update the URL accordingly. If you downloaded a ZIP, extract it and open a terminal in the extracted `codesloth` directory.

### 2. Configure and start the backend

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Backend API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### 3. Configure and start the frontend

In a second terminal, from the project root:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 4. Analyze a repository

Paste a public GitHub repository URL into CodeSloth and start the analysis. After indexing finishes, use the project tree, Dependency graph, and Architecture flow views to explore the codebase.

For a first test, try a public repository such as `https://github.com/tiangolo/fastapi`. Larger repositories may take longer to clone and index.

## Enable local AI with Ollama (optional)

1. Install and start [Ollama](https://ollama.com/).
2. Download a model, for example:

   ```bash
   ollama pull qwen2.5-coder:7b
   ```

3. Check `backend/.env` and set the model name to the model you actually installed:

   ```env
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   OLLAMA_MODEL=qwen2.5-coder:7b
   OLLAMA_TIMEOUT_SECONDS=90
   ```

4. Restart the backend after editing `.env`.
5. Check `http://127.0.0.1:8000/api/ai/status` to inspect AI availability.

If your installed model is `qwen2.5:3b`, set `OLLAMA_MODEL=qwen2.5:3b` instead. The configured model name must match a model shown by `ollama list`. Model speed and quality depend on your hardware and the model you choose.

## Configuration

Backend settings are documented in `backend/.env.example`:

| Variable | Purpose |
| --- | --- |
| `OLLAMA_BASE_URL` | Ollama API base URL |
| `OLLAMA_MODEL` | Local model name to use for Q&A |
| `OLLAMA_TIMEOUT_SECONDS` | Timeout for Ollama requests |
| `MAX_REPO_FILES` | Maximum number of files considered during indexing |
| `MAX_FILE_BYTES` | Maximum size of a file considered for indexing |
| `CLONE_TIMEOUT_SECONDS` | Timeout for cloning a repository |

Frontend API configuration is in `frontend/.env.local.example`:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | URL of the CodeSloth FastAPI backend |

## API overview

The local backend exposes these main endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Backend health check |
| `GET /api/ai/status` | Check local AI/model availability |
| `POST /api/analyze` | Analyze a public GitHub repository (`repo_url`) |
| `GET /api/analysis/{id}` | Retrieve a saved analysis |
| `GET /api/analysis/{id}/file?path=...` | Retrieve indexed details for a file |
| `POST /api/ask` | Ask a question about an analysis |

Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Project layout

```text
codesloth/
├── backend/
│   ├── main.py             # FastAPI API, repository analysis and AI integration
│   ├── requirements.txt
│   └── tests/              # Backend helper tests
├── frontend/
│   ├── app/
│   │   ├── page.tsx        # Main CodeSloth interface and graph views
│   │   └── globals.css
│   ├── lib/api.ts          # Frontend API client
│   └── package.json
├── .gitignore
└── README.md
```

## Safety, privacy, and limitations

- **Public repositories only:** the current workflow does not authenticate to access private GitHub repositories.
- **Static analysis:** CodeSloth does not execute repository code or install the repository's dependencies.
- **Heuristic extraction:** import resolution and symbol detection are not compiler-grade. Dynamic imports, reflection, generated code, aliases, framework conventions, and runtime dispatch can be missed.
- **Architecture is inferred:** diagrams reflect patterns recognized in indexed source and configuration, not guaranteed runtime traffic. Verify important relationships in the code.
- **AI can be wrong:** generated explanations are suggestions grounded in retrieved excerpts; check them against the source.
- **Local storage:** analysis metadata and extracted snippets are stored locally in SQLite. Review local data handling before analyzing sensitive code.
- **Keep the backend private:** the default setup binds to localhost. Do not expose it publicly without adding appropriate authentication, authorization, rate limits, sandboxing, and resource controls.

## Development and tests

Backend tests can be run from the project root after installing backend requirements:

```bash
python -m pytest backend/tests -q
```

Frontend scripts are available from `frontend/`:

```bash
npm run lint
npm run build
```

## Roadmap ideas

- More robust language parsing with Tree-sitter
- Local-folder ingestion
- Improved framework-specific route and API tracing
- Better call-graph resolution and incremental indexing
- Exportable diagrams and architecture reports
- Optional private repository support with carefully scoped credentials

## Contributing

Issues, bug reports, feature suggestions, and pull requests are welcome. When reporting a graph or indexing issue, include the repository language/framework, the steps to reproduce it, and any relevant console or backend logs. Avoid sharing secrets or proprietary source code in public issues.

## License

CodeSloth is distributed under the license in [`LICENSE`](LICENSE).

---

**CodeSloth — less time spelunking through folders, more time understanding the system.**
