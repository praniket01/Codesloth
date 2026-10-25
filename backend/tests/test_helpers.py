import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import build_tree, build_architecture, extract_imports, extract_symbols, resolve_local_import, validate_repo_url, read_ts_aliases

def test_validate_github_url():
    assert validate_repo_url("https://github.com/owner/repo") == ("owner", "repo")

def test_reject_non_github_url():
    try:
        validate_repo_url("https://example.com/owner/repo")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("Expected invalid URL to be rejected")

def test_extract_imports_and_symbols():
    source = "import { thing } from './thing';\nexport function greet(name: string) {\n return name;\n}\n"
    assert "./thing" in extract_imports("src/app.ts", source)
    assert any(s["name"] == "greet" for s in extract_symbols("src/app.ts", source))

def test_resolve_local_import():
    assert resolve_local_import("./thing", "src/app.ts", {"src/app.ts", "src/thing.ts"}) == "src/thing.ts"

def test_build_tree():
    tree = build_tree(["src/app.ts", "README.md"])
    assert tree["name"] == "."
    assert any(item["name"] == "src" for item in tree["children"])


def test_resolve_index_module_and_typescript_alias():
    paths = {"src/app.tsx", "src/components/Button/index.tsx", "src/lib/api.ts"}
    assert resolve_local_import("./components/Button", "src/app.tsx", paths) == "src/components/Button/index.tsx"
    assert resolve_local_import("@/lib/api", "src/app.tsx", paths, {"@/*": "src/*"}) == "src/lib/api.ts"


def test_resolve_python_module_imports():
    paths = {"app/main.py", "app/services/auth.py", "app/models/user.py"}
    assert resolve_local_import("app.services.auth", "app/main.py", paths) == "app/services/auth.py"
    assert resolve_local_import(".auth", "app/services/auth.py", paths) == "app/services/auth.py"


def test_build_architecture_layers_and_evidence_edges():
    records = {
        "frontend/app/page.tsx": {"snippet": 'fetch("/api/users")'},
        "backend/routes/users.py": {"snippet": '@app.get("/api/users")'},
        "backend/services/users.py": {"snippet": 'db.execute("select * from users")'},
        "backend/schema.sql": {"snippet": "CREATE TABLE users (id int);"},
    }
    edges = [
        {"id": "e1", "source": "frontend/app/page.tsx", "target": "backend/routes/users.py", "label": "imports"},
        {"id": "e2", "source": "backend/routes/users.py", "target": "backend/services/users.py", "label": "imports"},
    ]
    architecture = build_architecture(records, edges)
    node_ids = {node["id"] for node in architecture["nodes"]}
    assert {"frontend", "api", "backend", "data"}.issubset(node_ids)
    assert any(edge["source"] == "backend" and edge["target"] == "data" for edge in architecture["edges"])
    assert "inferred" in architecture["note"]
