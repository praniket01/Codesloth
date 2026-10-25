from __future__ import annotations
import os, re, json, uuid, sqlite3, tempfile, subprocess
from pathlib import Path
from collections import Counter
from typing import Any
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).with_name(".env"))
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "codesloth.db"
MAX_REPO_FILES = int(os.getenv("MAX_REPO_FILES", "2500"))
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", "300000"))
CLONE_TIMEOUT = int(os.getenv("CLONE_TIMEOUT_SECONDS", "90"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "coverage", ".venv", "venv", "__pycache__", "vendor", "target", "Pods", ".idea", ".vscode"}
TEXT_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".cs", ".go", ".rs", ".php", ".rb", ".vue", ".svelte", ".json", ".yaml", ".yml", ".toml", ".md", ".sql", ".sh", ".html", ".css", ".scss"}
SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".cs", ".go", ".rs", ".php", ".rb", ".vue", ".svelte"}

app = FastAPI(title="CodeSloth API", version="0.1.0", description="Local-first codebase explorer")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    repo_url: str = Field(min_length=10, max_length=500)
class AskRequest(BaseModel):
    analysis_id: str
    question: str = Field(min_length=3, max_length=1500)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
with db() as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, repo_url TEXT NOT NULL, repo_name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, payload TEXT NOT NULL)""")

def validate_repo_url(url: str) -> tuple[str, str]:
    m = re.fullmatch(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url.strip())
    if not m or m.group(1) in {".", ".."} or m.group(2) in {".", ".."}:
        raise HTTPException(status_code=400, detail="Use a public GitHub URL like https://github.com/owner/repository")
    return m.group(1), m.group(2)

def clone_repo(url: str, destination: str):
    try:
        result = subprocess.run(["git", "clone", "--depth", "1", url, destination], capture_output=True, text=True, timeout=CLONE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Repository clone timed out. Try a smaller repository.")
    if result.returncode:
        raise HTTPException(status_code=400, detail="Could not clone repository. Confirm it is public and URL is correct. " + (result.stderr or "")[-500:])

def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f: return b"\0" in f.read(4096)
    except OSError: return True

def language_for(path: Path) -> str:
    return {".py":"Python",".js":"JavaScript",".jsx":"JavaScript/React",".ts":"TypeScript",".tsx":"TypeScript/React",".cs":"C#",".java":"Java",".go":"Go",".rs":"Rust",".php":"PHP",".rb":"Ruby",".vue":"Vue",".svelte":"Svelte",".sql":"SQL",".html":"HTML",".css":"CSS",".scss":"SCSS",".json":"JSON",".yaml":"YAML",".yml":"YAML",".md":"Markdown",".sh":"Shell"}.get(path.suffix.lower(), "Other")

def extract_imports(path: str, content: str) -> list[str]:
    ext = Path(path).suffix.lower()
    if ext == ".py": patterns = [r"^\s*from\s+([.\w]+)\s+import\s+", r"^\s*import\s+([.\w]+)"]
    elif ext in {".js",".jsx",".ts",".tsx",".mjs",".cjs",".vue",".svelte"}:
        patterns = [r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+)['"]([^'"]+)['"]""", r"""require\(\s*['"]([^'"]+)['"]\s*\)""", r"""import\(\s*['"]([^'"]+)['"]\s*\)"""]
    elif ext == ".cs": patterns = [r"^\s*using\s+([\w.]+)\s*;"]
    else: patterns = []
    found=[]
    for pattern in patterns: found.extend(re.findall(pattern, content, re.MULTILINE))
    return list(dict.fromkeys(found))[:80]

def extract_symbols(path: str, content: str) -> list[dict[str, Any]]:
    ext = Path(path).suffix.lower()
    if ext == ".py": patterns = [(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", "function"), (r"^\s*class\s+([A-Za-z_]\w*)\b", "class")]
    elif ext in {".js",".jsx",".ts",".tsx",".mjs",".cjs",".vue",".svelte"}:
        patterns = [(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", "function"), (r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", "class"), (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "function")]
    elif ext == ".cs": patterns = [(r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?(?:[\w<>\[\],.?]+\s+)+([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:\{|=>)", "method"), (r"^\s*(?:public|internal)?\s*class\s+([A-Za-z_]\w*)", "class")]
    else: patterns=[]
    result=[]
    for line_no,line in enumerate(content.splitlines(),1):
        for pattern,kind in patterns:
            m=re.search(pattern,line)
            if m: result.append({"name":m.group(1),"kind":kind,"line":line_no}); break
    return result[:300]

def build_tree(paths: list[str]) -> dict[str, Any]:
    root={"name":".","type":"directory","children":{}}
    for path in paths:
        node=root; parts=path.split("/")
        for i,part in enumerate(parts):
            children=node["children"]
            if part not in children: children[part]={"name":part,"type":"directory" if i<len(parts)-1 else "file","path":"/".join(parts[:i+1]),"children":{}}
            node=children[part]
    def finalize(node):
        children=node.pop("children",{})
        node["children"]=sorted([finalize(v) for v in children.values()],key=lambda x:(x["type"]!="directory",x["name"].lower()))
        if node["type"]=="file": node.pop("children",None)
        return node
    return finalize(root)

def _resolve_path_candidate(candidate: str, paths: set[str]) -> str | None:
    """Resolve a path stem against common source extensions and index modules."""
    normalized = str(Path(candidate))
    extensions = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".cs", ".java", ".go", ".rs", ".php", ".rb")
    options = [normalized]
    if not Path(normalized).suffix:
        options.extend(normalized + ext for ext in extensions)
    options.extend(f"{normalized}/index{ext}" for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
    options.append(f"{normalized}/__init__.py")
    for item in options:
        if item in paths:
            return item
    return None

def resolve_local_import(source: str, importer: str, paths: set[str], aliases: dict[str, str] | None = None) -> str | None:
    """Resolve relative imports, TS path aliases, and Python module imports to indexed files."""
    source = source.strip()
    importer_path = Path(importer)
    candidates: list[str] = []
    if importer_path.suffix.lower() == ".py":
        # Python imports use dotted module names rather than relative file paths.
        module_path = source.lstrip(".").replace(".", "/")
        if source.startswith("."):
            base = importer_path.parent
            dots = len(source) - len(source.lstrip("."))
            for _ in range(max(0, dots - 1)):
                base = base.parent
            candidates.append((base / module_path).as_posix())
        else:
            candidates.append(module_path)
    elif source.startswith("."):
        candidates.append((importer_path.parent / source).as_posix())
    else:
        for alias, target in (aliases or {}).items():
            prefix = alias[:-1] if alias.endswith("*") else alias
            if source == prefix or source.startswith(prefix):
                suffix = source[len(prefix):].lstrip("/")
                target_prefix = target[:-1] if target.endswith("*") else target
                candidates.append((Path(target_prefix) / suffix).as_posix())
        # Do not treat arbitrary third-party package imports as local files.
    for candidate in candidates:
        resolved = _resolve_path_candidate(candidate, paths)
        if resolved:
            return resolved
    return None

def read_ts_aliases(root: Path) -> dict[str, str]:
    """Read simple baseUrl/paths aliases from tsconfig.json or jsconfig.json."""
    aliases: dict[str, str] = {}
    for config_name in ("tsconfig.json", "jsconfig.json"):
        config_path = root / config_name
        if not config_path.is_file():
            continue
        try:
            raw = config_path.read_text(encoding="utf-8")
            raw = re.sub(r"/\*.*?\*/|(^|\s)//.*?$", "", raw, flags=re.MULTILINE | re.DOTALL)
            config = json.loads(raw)
            options = config.get("compilerOptions", {})
            base_url = options.get("baseUrl", ".")
            base_path = Path(base_url)
            for pattern, targets in options.get("paths", {}).items():
                if not targets:
                    continue
                target = str(base_path / targets[0])
                aliases[pattern] = target
        except (OSError, ValueError, TypeError):
            continue
    return aliases

def classify_architecture_file(path: str, record: dict[str, Any]) -> str:
    """Heuristically classify indexed files for an evidence-based architecture overview."""
    p = path.lower()
    text = str(record.get("snippet", "")).lower()
    name = Path(path).name.lower()
    if any(part in p for part in ("/test", "/tests/", "__tests__", ".test.", ".spec.")) or name.startswith("test_"):
        return "tests"
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "nginx.conf", "makefile"} or any(x in p for x in ("/deploy", "/infra", "/k8s", "terraform")):
        return "infrastructure"
    if name in {"package.json", "tsconfig.json", "jsconfig.json", "requirements.txt", "pyproject.toml", "poetry.lock", ".env.example", "vite.config.ts", "next.config.ts", "webpack.config.js"} or p.endswith((".yaml", ".yml", ".toml")):
        if any(x in p for x in ("openapi", "swagger")):
            return "api"
        return "configuration"
    if p.endswith((".sql", ".prisma")) or any(x in p for x in ("/migration", "/migrations", "/schema", "/models/", "/entities/")) or name in {"database.py", "db.py", "database.ts", "db.ts", "context.cs", "applicationdbcontext.cs"}:
        return "data"
    if any(x in p for x in ("/api/", "/apis/", "/routes/", "/controllers/", "openapi", "swagger")) or re.search(r"(@app\.(get|post|put|delete|patch)|@router\.|\[http(get|post|put|delete)|map(get|post|put|delete)|app\.(get|post|put|delete)|router\.(get|post|put|delete))", text):
        return "api"
    if (p.startswith(("frontend/", "client/", "src/components/", "src/pages/", "app/", "components/", "pages/", "ui/")) or any(x in p for x in ("/frontend/", "/client/", "/components/", "/pages/", "/app/", "/ui/"))) or Path(path).suffix.lower() in {".tsx", ".jsx", ".vue", ".svelte", ".html", ".css", ".scss"}:
        if re.search(r"\b(fetch\(|axios\.|httpclient|baseurl|api_url|apiurl)\b", text):
            return "frontend-api-client"
        return "frontend"
    if re.search(r"\b(fetch\(|axios\.|httpclient|requests\.(get|post|put|delete)|https?://)\b", text):
        return "integrations"
    if any(x in p for x in ("/services/", "/service/", "/domain/", "/business/", "/repository/", "/repositories/", "/middleware/", "/workers/")) or Path(path).suffix.lower() in {".py", ".cs", ".java", ".go", ".rs", ".php", ".rb"}:
        return "backend"
    return "other"

def build_architecture(records: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a conservative layer-level flow from indexed files and detected import/call evidence."""
    labels = {
        "frontend": ("Frontend UI", "Pages, components and user-facing code", 0, "#7769d8"),
        "frontend-api-client": ("API clients", "Frontend HTTP clients and request wrappers", 1, "#4c8fd7"),
        "api": ("API / routes", "Detected route handlers and API definitions", 2, "#4bafba"),
        "backend": ("Backend services", "Business logic, services and server modules", 3, "#4da58a"),
        "data": ("Data layer", "Database schemas, models, migrations and SQL", 4, "#d2a052"),
        "integrations": ("External integrations", "HTTP clients and external service references", 4, "#c27ab5"),
        "configuration": ("Configuration", "Project manifests and runtime configuration", 1, "#7c8ca6"),
        "infrastructure": ("Infrastructure", "Deployment and runtime infrastructure files", 1, "#7c8ca6"),
        "tests": ("Tests", "Detected test files", 1, "#7c8ca6"),
        "other": ("Other modules", "Files that could not be confidently classified", 2, "#64748b"),
    }
    groups: dict[str, list[str]] = {}
    for path, record in records.items():
        group = classify_architecture_file(path, record)
        groups.setdefault(group, []).append(path)
    nodes = []
    for group, paths in groups.items():
        title, description, layer, color = labels[group]
        nodes.append({"id": group, "label": title, "description": description, "layer": layer, "color": color, "file_count": len(paths), "files": sorted(paths)[:80]})
    by_path = {path: classify_architecture_file(path, record) for path, record in records.items()}
    counts: Counter[tuple[str, str, str]] = Counter()
    for edge in edges:
        source = by_path.get(edge["source"]); target = by_path.get(edge["target"])
        if source and target and source != target:
            counts[(source, target, "imports")] += 1
    # Add likely request/data-flow edges only when the corresponding evidence exists in indexed source.
    text_by_group: dict[str, str] = {}
    for path, record in records.items():
        group = by_path[path]
        text_by_group[group] = text_by_group.get(group, "") + "\n" + str(record.get("snippet", "")).lower()
    if "frontend" in groups and "api" in groups and ("frontend-api-client" in groups or re.search(r"\b(fetch\(|axios\.|httpclient|/api/)\b", text_by_group.get("frontend", "") + text_by_group.get("frontend-api-client", ""))):
        counts[("frontend", "api", "request flow (inferred)")] += 1
    if "frontend-api-client" in groups and "api" in groups:
        counts[("frontend-api-client", "api", "HTTP request (inferred)")] += 1
    if "api" in groups and "backend" in groups:
        counts[("api", "backend", "handler / service (inferred)")] += 1
    if "backend" in groups and "data" in groups and re.search(r"\b(dbcontext|sqlalchemy|mongoose|prisma|repository|session\.query|execute\(|select .* from|insert into)\b", text_by_group.get("backend", "")):
        counts[("backend", "data", "data access (inferred)")] += 1
    if "backend" in groups and "integrations" in groups:
        counts[("backend", "integrations", "external call (inferred)")] += 1
    arch_edges = []
    for (source, target, label), weight in counts.items():
        if source in groups and target in groups:
            arch_edges.append({"id": f"{source}->{target}:{label}", "source": source, "target": target, "label": label, "weight": weight})
    return {"nodes": nodes, "edges": arch_edges, "note": "Architecture is inferred from indexed paths, imports, route patterns and code/config hints. Inferred connections are labelled; verify them against source."}


def analyze_repo(repo_url: str) -> dict[str, Any]:
    owner,repo=validate_repo_url(repo_url)
    with tempfile.TemporaryDirectory(prefix="codesloth-") as temp:
        checkout=os.path.join(temp,"repo"); clone_repo(repo_url,checkout); root=Path(checkout)
        records={}; paths=[]
        for current,dirs,filenames in os.walk(root):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for filename in filenames:
                path=Path(current)/filename; rel=path.relative_to(root).as_posix()
                if path.suffix.lower() not in TEXT_EXTS or path.stat().st_size>MAX_FILE_BYTES or is_binary(path): continue
                try: content=path.read_text(encoding="utf-8",errors="replace")
                except OSError: continue
                records[rel]={"path":rel,"language":language_for(path),"size":path.stat().st_size,"imports":extract_imports(rel,content),"symbols":extract_symbols(rel,content) if path.suffix.lower() in SOURCE_EXTS else [],"snippet":content[:12000]}
                paths.append(rel)
                if len(records)>=MAX_REPO_FILES: break
            if len(records)>=MAX_REPO_FILES: break
        if not records: raise HTTPException(status_code=400,detail="No supported text files found in this repository.")
        pathset=set(records); nodes=[]; edges=[]
        aliases = read_ts_aliases(root)
        for rel,record in records.items():
            nodes.append({"id":rel,"label":Path(rel).name,"type":"file","language":record["language"],"symbols_count":len(record["symbols"])})
            for source in record["imports"]:
                resolved=resolve_local_import(source,rel,pathset,aliases)
                if resolved and resolved!=rel: edges.append({"id":f"{rel}->{resolved}","source":rel,"target":resolved,"type":"imports","label":"imports"})
        top=Counter(p.split("/")[0] for p in paths if "/" in p)
        langs=Counter(r["language"] for r in records.values())
        return {"repo_url":f"https://github.com/{owner}/{repo}","repo_name":f"{owner}/{repo}","tree":build_tree(paths),"summary":{"file_count":len(records),"language_counts":dict(langs.most_common()),"top_level":dict(top.most_common(15)),"truncated":len(records)>=MAX_REPO_FILES},"nodes":nodes,"edges":edges,"architecture":build_architecture(records, edges),"files":records}

@app.get("/")
def root(): return {"name":"CodeSloth API","docs":"/docs","health":"/health"}
@app.get("/health")
def health(): return {"status":"ok","service":"codesloth-api"}
@app.get("/api/ai/status")
def ai_status():
    try:
        r=requests.get(f"{OLLAMA_BASE_URL}/api/tags",timeout=3); r.raise_for_status()
        return {"available":True,"model":OLLAMA_MODEL,"models":[m.get("name") for m in r.json().get("models",[])]}
    except Exception: return {"available":False,"model":OLLAMA_MODEL,"message":"Ollama is optional. Start Ollama and pull the configured model to enable AI explanations."}

@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    payload=analyze_repo(request.repo_url); analysis_id=str(uuid.uuid4())
    with db() as conn: conn.execute("INSERT INTO analyses (id,repo_url,repo_name,payload) VALUES (?,?,?,?)",(analysis_id,payload["repo_url"],payload["repo_name"],json.dumps(payload)))
    return {"analysis_id":analysis_id,**{k:v for k,v in payload.items() if k!="files"}}

@app.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: str):
    with db() as conn: row=conn.execute("SELECT payload FROM analyses WHERE id=?",(analysis_id,)).fetchone()
    if not row: raise HTTPException(status_code=404,detail="Analysis not found")
    payload=json.loads(row["payload"]); payload.pop("files",None)
    return {"analysis_id":analysis_id,**payload}

@app.get("/api/analysis/{analysis_id}/file")
def get_file(analysis_id: str,path: str=Query(...,min_length=1,max_length=500)):
    with db() as conn: row=conn.execute("SELECT payload FROM analyses WHERE id=?",(analysis_id,)).fetchone()
    if not row: raise HTTPException(status_code=404,detail="Analysis not found")
    record=json.loads(row["payload"]).get("files",{}).get(path)
    if not record: raise HTTPException(status_code=404,detail="File not found in this analysis")
    return {"path":path,"language":record["language"],"size":record["size"],"imports":record["imports"],"symbols":record["symbols"],"content":record["snippet"]}

def relevant_files(files: dict[str,Any],question: str,limit=5):
    terms={t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}",question)}
    ranked=[]
    for path,rec in files.items():
        searchable=(path+" "+" ".join(s["name"] for s in rec["symbols"])+" "+" ".join(rec["imports"])).lower()
        score=sum(term in searchable for term in terms)
        q=question.lower()
        if any(k in q for k in ["auth","login","sign in"]) and any(k in searchable for k in ["auth","login","identity"]): score+=3
        if any(k in q for k in ["database","persist","store","repository"]) and any(k in searchable for k in ["database","repository","db","model"]): score+=2
        if score: ranked.append((score,path,rec))
    ranked.sort(key=lambda x:(-x[0],x[1]))
    return ranked[:limit] or [(0,p,r) for p,r in list(files.items())[:limit]]

@app.post("/api/ask")
def ask(request: AskRequest):
    with db() as conn: row=conn.execute("SELECT payload FROM analyses WHERE id=?",(request.analysis_id,)).fetchone()
    if not row: raise HTTPException(status_code=404,detail="Analysis not found. Analyze the repository first.")
    payload=json.loads(row["payload"]); selected=relevant_files(payload.get("files",{}),request.question)
    evidence="\n\n".join(f"FILE: {p}\nLANGUAGE: {r['language']}\nIMPORTS: {', '.join(r['imports'][:12])}\nSYMBOLS: {', '.join(s['name'] for s in r['symbols'][:30])}\nSOURCE EXCERPT:\n{r['snippet'][:5000]}" for _,p,r in selected)
    prompt=f"""You are CodeSloth, a careful codebase guide. Answer only using repository evidence. If evidence is insufficient, say so. Never invent paths or behavior. Explain likely flow concisely and cite paths and line numbers when known.
Repository: {payload.get('repo_name')}
Question: {request.question}
Evidence:
{evidence}
Return (1) explanation, (2) numbered flow if applicable, (3) files to inspect, (4) uncertainties."""
    try:
        r=requests.post(f"{OLLAMA_BASE_URL}/api/generate",json={"model":OLLAMA_MODEL,"prompt":prompt,"stream":False},timeout=OLLAMA_TIMEOUT); r.raise_for_status()
        answer=r.json().get("response","").strip()
        if not answer: raise ValueError("Empty response")
        mode="ollama"
    except Exception:
        answer="Ollama is unavailable, so this is an index-based fallback rather than an AI explanation. Start with these relevant files:\n\n"+"\n".join(f"- `{p}` — {r['language']}; symbols: {', '.join(s['name'] for s in r['symbols'][:8]) or 'none extracted'}; imports: {', '.join(r['imports'][:6]) or 'none extracted'}" for _,p,r in selected)+"\n\nStart Ollama and pull the configured model to enable natural-language explanations."
        mode="index-fallback"
    return {"question":request.question,"answer":answer,"mode":mode,"evidence":[{"path":p,"language":r["language"],"symbols":r["symbols"][:20]} for _,p,r in selected]}
