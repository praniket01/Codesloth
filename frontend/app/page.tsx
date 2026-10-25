"use client";

import { useCallback, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, MiniMap, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, API_URL } from "@/lib/api";
import { ArrowRight, BrainCircuit, Check, ChevronDown, ChevronRight, Code2, ExternalLink, FileCode2, Folder, FolderOpen, GitBranch, Github, LoaderCircle, Search, ShieldCheck, Sparkles, Workflow, X } from "lucide-react";

type TreeNode = { name: string; type: "directory" | "file"; path?: string; children?: TreeNode[] };
type Summary = { file_count: number; language_counts: Record<string, number>; top_level: Record<string, number>; truncated: boolean };
type ArchNode = { id: string; label: string; description: string; layer: number; color: string; file_count: number; files: string[] };
type ArchEdge = { id: string; source: string; target: string; label: string; weight: number };
type Analysis = { analysis_id: string; repo_url: string; repo_name: string; tree: TreeNode; summary: Summary; nodes: {id:string;label:string;language:string;symbols_count:number}[]; edges: {id:string;source:string;target:string;label:string}[]; architecture?: { nodes: ArchNode[]; edges: ArchEdge[]; note: string } };
type FileDetail = { path: string; language: string; size: number; imports: string[]; symbols: {name:string;kind:string;line:number}[]; content: string };
type Answer = { answer: string; mode: string; evidence: {path:string;language:string;symbols:{name:string;kind:string;line:number}[]}[] };

function TreeItem({ item, onSelect, selected, depth = 0 }: { item: TreeNode; onSelect: (path: string) => void; selected: string; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);
  const dir = item.type === "directory";
  return <div>
    <button className={`tree-row ${selected === item.path ? "selected" : ""}`} style={{ paddingLeft: 9 + depth * 13 }} onClick={() => dir ? setOpen(!open) : item.path && onSelect(item.path)}>
      {dir ? (open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>) : <span className="tree-spacer"/>}
      {dir ? (open ? <FolderOpen size={14}/> : <Folder size={14}/>) : <FileCode2 size={14}/>}
      <span>{item.name}</span>
    </button>
    {dir && open && item.children?.map(child => <TreeItem key={child.path || child.name} item={child} onSelect={onSelect} selected={selected} depth={depth+1}/>)}
  </div>;
}

export default function Home() {
  const [repoUrl, setRepoUrl] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<FileDetail | null>(null);
  const [question, setQuestion] = useState("Where is authentication implemented?");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<"overview"|"graph"|"architecture">("overview");
  const [aiAvailable, setAiAvailable] = useState<boolean | null>(null);

  const analyze = async (event?: React.FormEvent) => {
    event?.preventDefault(); setLoading(true); setError(""); setAnalysis(null); setFile(null); setAnswer(null);
    try {
      const result = await api<Analysis>("/api/analyze", { method: "POST", body: JSON.stringify({ repo_url: repoUrl }) });
      setAnalysis(result);
      api<{available:boolean}>("/api/ai/status").then(s => setAiAvailable(s.available)).catch(() => setAiAvailable(false));
    } catch (e) { setError(e instanceof Error ? e.message : "Analysis failed"); }
    finally { setLoading(false); }
  };
  const selectFile = useCallback(async (path: string) => {
    if (!analysis) return;
    try { setFile(await api<FileDetail>(`/api/analysis/${analysis.analysis_id}/file?path=${encodeURIComponent(path)}`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load file"); }
  }, [analysis]);
  const ask = async (event?: React.FormEvent) => {
    event?.preventDefault(); if (!analysis || !question.trim()) return;
    setAsking(true); setError("");
    try { setAnswer(await api<Answer>("/api/ask", { method: "POST", body: JSON.stringify({ analysis_id: analysis.analysis_id, question }) })); }
    catch (e) { setError(e instanceof Error ? e.message : "Question failed"); }
    finally { setAsking(false); }
  };
  const graph = useMemo(() => {
    if (!analysis) return { nodes: [], edges: [], totalNodes: 0, totalEdges: 0 };
    const needle = filter.trim().toLowerCase();
    const visible = analysis.nodes.filter(n => !needle || n.id.toLowerCase().includes(needle) || n.language.toLowerCase().includes(needle));
    const ids = new Set(visible.map(n => n.id));
    const visibleEdges = analysis.edges.filter(e => ids.has(e.source) && ids.has(e.target));

    // Assign layers from dependency relationships instead of directory depth. Any
    // cyclic/unreachable nodes are placed in a fallback layer, never discarded.
    const indegree = new Map(visible.map(n => [n.id, 0]));
    const outgoing = new Map<string, string[]>();
    for (const edge of visibleEdges) {
      indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
      outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target]);
    }
    const queue = visible.filter(n => (indegree.get(n.id) || 0) === 0).map(n => n.id);
    const rank = new Map<string, number>();
    for (const id of queue) rank.set(id, 0);
    let cursor = 0;
    while (cursor < queue.length) {
      const id = queue[cursor++];
      for (const target of outgoing.get(id) || []) {
        rank.set(target, Math.max(rank.get(target) || 0, (rank.get(id) || 0) + 1));
        const remaining = (indegree.get(target) || 0) - 1;
        indegree.set(target, remaining);
        if (remaining === 0) queue.push(target);
      }
    }
    const unresolved = visible.filter(n => !rank.has(n.id));
    for (const n of unresolved) rank.set(n.id, Math.max(0, n.id.split("/").length - 1));
    const buckets = new Map<number, string[]>();
    for (const n of visible) {
      const layer = rank.get(n.id) || 0;
      buckets.set(layer, [...(buckets.get(layer) || []), n.id]);
    }
    const rowById = new Map<string, number>();
    for (const idsInLayer of buckets.values()) {
      idsInLayer.sort((a, b) => a.localeCompare(b));
      idsInLayer.forEach((id, row) => rowById.set(id, row));
    }
    const nodes = visible.map(n => {
      const layer = rank.get(n.id) || 0;
      const row = rowById.get(n.id) || 0;
      return { id: n.id, position: { x: layer * 300, y: row * 105 }, data: { label: <div className="graph-node"><FileCode2 size={14}/><div><strong>{n.label}</strong><small>{n.language} · {n.symbols_count} symbols</small></div></div> }, style: { width: 220, borderRadius: 12, border: "1px solid #29374d", background: "#0d1524", color: "#e5edf9", padding: 10 }, sourcePosition: "right" as const, targetPosition: "left" as const };
    });
    const edges = visibleEdges.map(e => ({ id: e.id, source: e.source, target: e.target, label: e.label, markerEnd: { type: MarkerType.ArrowClosed, color: "#7185a5" }, style: { stroke: "#536783", strokeWidth: 1.3 }, labelStyle: { fill: "#9eb0cb", fontSize: 10 } }));
    return { nodes, edges, totalNodes: analysis.nodes.length, totalEdges: analysis.edges.length };
  }, [analysis, filter]);

  const architectureGraph = useMemo(() => {
    const architecture = analysis?.architecture;
    if (!architecture) return { nodes: [], edges: [], totalNodes: 0, totalEdges: 0 };
    const layers = new Map<number, ArchNode[]>();
    architecture.nodes.forEach(node => layers.set(node.layer, [...(layers.get(node.layer) || []), node]));
    const row = new Map<string, number>();
    layers.forEach(items => items.forEach((item, index) => row.set(item.id, index)));
    const nodes = architecture.nodes.map(node => ({
      id: node.id,
      position: { x: node.layer * 300, y: (row.get(node.id) || 0) * 150 },
      data: { label: <div className="architecture-node"><div className="architecture-node-top"><span className="architecture-dot" style={{ background: node.color }} /><strong>{node.label}</strong><span className="architecture-count">{node.file_count}</span></div><small>{node.description}</small><small className="architecture-files">{node.files.slice(0, 2).join(" · ")}{node.file_count > 2 ? ` +${node.file_count - 2} more` : ""}</small></div> },
      style: { width: 245, borderRadius: 12, border: `1px solid ${node.color}88`, background: "#0d1524", color: "#e5edf9", padding: 12 },
      sourcePosition: "right" as const, targetPosition: "left" as const,
    }));
    const edges = architecture.edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, label: edge.label, markerEnd: { type: MarkerType.ArrowClosed, color: "#7185a5" }, style: { stroke: "#536783", strokeWidth: Math.min(3, 1 + Math.log2(edge.weight + 1) / 2) }, labelStyle: { fill: "#9eb0cb", fontSize: 9 }, labelBgStyle: { fill: "#0b1220", fillOpacity: 0.92 } }));
    return { nodes, edges, totalNodes: nodes.length, totalEdges: edges.length };
  }, [analysis]);

  return <main className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#"><span className="brand-mark">🦥</span><span>code<span className="accent">sloth</span><small>CODEBASE EXPLORER</small></span></a>
      <div className="side-label">WORKSPACE</div><div className="workspace"><span className="workspace-dot"/><div><strong>Local workspace</strong><small>Private by default</small></div></div>
      <div className="side-label">EXPLORE</div>
      <button className={`nav-item ${view==="overview"?"active":""}`} onClick={()=>setView("overview")}><FolderOpen size={17}/> Project overview</button>
      <button className={`nav-item ${view==="graph"?"active":""}`} onClick={()=>setView("graph")}><GitBranch size={17}/> Dependency graph</button><button className={`nav-item ${view==="architecture"?"active":""}`} onClick={()=>setView("architecture")}><Workflow size={17}/> Architecture flow</button>
      <a className="nav-item" href="#ask"><BrainCircuit size={17}/> Ask your codebase</a>
      <div className="sidebar-bottom"><div className="local-card"><ShieldCheck size={18}/><div><strong>Local-first AI</strong><small>{aiAvailable===true?"Ollama connected":aiAvailable===false?"Index works without AI":"AI status checked after scan"}</small></div><span className={`status-dot ${aiAvailable?"online":""}`}/></div><small className="sidebar-foot">Open models. Your machine. Your pace.</small></div>
    </aside>
    <section className="main-area">
      <header className="topbar"><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14}/><strong>{analysis?.repo_name||"New analysis"}</strong></div><div className="top-actions"><span className="pill"><span className="tiny-dot"/> API {API_URL.replace("http://","")}</span><a className="icon-button" href={`${API_URL}/docs`} target="_blank" rel="noreferrer" title="API docs"><ExternalLink size={16}/></a></div></header>
      <div className="content">
        <div className="hero-row"><div><div className="eyebrow"><Sparkles size={14}/> YOUR LAZY DEVELOPER SUPERPOWER</div><h1>Meet your codebase.<br/><span className="gradient-text">Without the awkward small talk.</span></h1><p className="hero-copy">Map the architecture, follow dependencies, and find where features live — without spending your afternoon spelunking through folders.</p></div><div className="hero-sloth">🦥<span className="orbit orbit-one"/><span className="orbit orbit-two"/></div></div>
        <form className="repo-form" onSubmit={analyze}><div className="repo-input-wrap"><Github size={19}/><input aria-label="GitHub repository URL" value={repoUrl} onChange={e=>setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repository" required/><span className="input-hint">PUBLIC REPO</span></div><button className="primary-button" disabled={loading}>{loading?<><LoaderCircle className="spin" size={16}/> Mapping…</>:<><Sparkles size={16}/> Map this repo <ArrowRight size={16}/></>}</button></form>
        <div className="privacy-note"><ShieldCheck size={14}/> Indexing runs locally. Public repository required. Project code is never executed.</div>
        {error&&<div className="error-banner"><X size={16}/>{error}</div>}
        {!analysis&&<div className="empty-state"><div className="empty-icon"><GitBranch size={30}/></div><h2>Your next codebase, decoded.</h2><p>Paste a public GitHub repository URL to generate its file map and dependency graph.</p><div className="feature-cards"><div><FolderOpen size={18}/><strong>Project DNA</strong><span>Understand the folder hierarchy.</span></div><div><GitBranch size={18}/><strong>Dependency map</strong><span>See local imports connect.</span></div><div><BrainCircuit size={18}/><strong>Ask locally</strong><span>Get answers grounded in files.</span></div></div><button className="example-link" onClick={()=>setRepoUrl("https://github.com/tiangolo/fastapi")}>Try an example repository <ArrowRight size={15}/></button></div>}
        {analysis&&<>
          <div className="repo-title-row"><div className="repo-avatar"><Github size={22}/></div><div className="repo-heading"><h2>{analysis.repo_name}</h2><a href={analysis.repo_url} target="_blank" rel="noreferrer">{analysis.repo_url} <ExternalLink size={12}/></a></div><span className="indexed-pill"><Check size={13}/> INDEXED</span></div>
          <div className="stats-grid"><div className="stat-card"><span>FILES INDEXED</span><strong>{analysis.summary.file_count.toLocaleString()}</strong><small><FileCode2 size={13}/> Source and config files</small></div><div className="stat-card"><span>DEPENDENCIES</span><strong>{analysis.edges.length.toLocaleString()}</strong><small><GitBranch size={13}/> Local import edges</small></div><div className="stat-card"><span>LANGUAGES</span><strong>{Object.keys(analysis.summary.language_counts).length}</strong><small><Code2 size={13}/> Detected file types</small></div><div className="stat-card"><span>AI EXPLANATIONS</span><strong>{aiAvailable?"Ready":"Optional"}</strong><small><BrainCircuit size={13}/> Ollama local model</small></div></div>
          {analysis.summary.truncated&&<div className="warning-banner">Repository file limit reached. Increase MAX_REPO_FILES to index more files.</div>}
          <div className="view-tabs"><button className={view==="overview"?"selected":""} onClick={()=>setView("overview")}><FolderOpen size={15}/> Project tree</button><button className={view==="graph"?"selected":""} onClick={()=>setView("graph")}><GitBranch size={15}/> Dependency graph <span>{analysis.edges.length}</span></button><button className={view==="architecture"?"selected":""} onClick={()=>setView("architecture")}><Workflow size={15}/> Architecture flow <span>{analysis.architecture?.nodes.length || 0}</span></button></div>
          {view==="overview" ? <div className="explorer-grid"><section className="panel tree-panel"><div className="panel-heading"><div><h3>Repository structure</h3><p>Click a file to inspect symbols and source.</p></div><span className="panel-count">{analysis.summary.file_count} files</span></div><div className="tree-scroll"><TreeItem item={analysis.tree} onSelect={selectFile} selected={file?.path||""}/></div></section><section className="panel file-panel"><div className="panel-heading"><div><h3>{file?.path||"File inspector"}</h3><p>{file?`${file.language} · ${file.size.toLocaleString()} bytes`:"Choose a file from the project tree"}</p></div>{file&&<button className="subtle-button" onClick={()=>setFile(null)}><X size={14}/></button>}</div>{file?<><div className="symbols-section"><h4>Symbols <span>{file.symbols.length}</span></h4>{file.symbols.length?file.symbols.map(s=><div className="symbol-row" key={`${s.name}-${s.line}`}><Code2 size={13}/><span>{s.name}</span><small>{s.kind} · L{s.line}</small></div>):<p className="muted">No symbols extracted from this file.</p>}</div><div className="imports-section"><h4>Imports <span>{file.imports.length}</span></h4>{file.imports.map(i=><span className="import-chip" key={i}>{i}</span>)}</div><pre className="source-preview"><code>{file.content}</code></pre></>:<div className="file-empty"><FileCode2 size={32}/><p>File details will appear here.</p><span>Browse folders and select a source file.</span></div>}</section></div> : view==="graph" ? <section className="panel graph-panel"><div className="panel-heading"><div><h3>Dependency graph</h3><p>Local imports only. Select a node to inspect its file.</p></div><div className="graph-search"><Search size={14}/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter files…"/></div></div><div className="graph-canvas"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView fitViewOptions={{ padding: 0.18, minZoom: 0.08, maxZoom: 1 }} onNodeClick={(_,node)=>selectFile(node.id)} minZoom={0.04} maxZoom={1.6} onlyRenderVisibleElements={true}><Background color="#26344a" gap={22}/><Controls/><MiniMap nodeColor="#253a56" maskColor="rgba(3,7,18,0.65)"/></ReactFlow></div><div className="graph-legend"><span><i className="legend-node"/> File node</span><span><i className="legend-edge"/> Local import relationship</span><span>{graph.nodes.length.toLocaleString()} / {graph.totalNodes.toLocaleString()} nodes · {graph.edges.length.toLocaleString()} / {graph.totalEdges.toLocaleString()} edges{filter ? " (filtered)" : ""}</span></div></section> : <section className="panel graph-panel"><div className="panel-heading"><div><h3><Workflow size={17}/> Architecture flow</h3><p>Inferred system blocks from source paths, imports, routes, and configuration.</p></div><span className="panel-count">{architectureGraph.totalNodes} blocks · {architectureGraph.totalEdges} connections</span></div><div className="architecture-note"><ShieldCheck size={14}/>{analysis.architecture?.note || "Architecture is inferred from indexed code and should be verified against source."}</div><div className="graph-canvas architecture-canvas"><ReactFlow nodes={architectureGraph.nodes} edges={architectureGraph.edges} fitView fitViewOptions={{ padding: 0.22, minZoom: 0.08, maxZoom: 1 }} onNodeClick={(_,node)=>{ const target = analysis.architecture?.nodes.find(n=>n.id===node.id)?.files[0]; if (target) { setView("overview"); selectFile(target); } }} minZoom={0.04} maxZoom={1.5} onlyRenderVisibleElements={true}><Background color="#26344a" gap={22}/><Controls/><MiniMap nodeColor={node=>String(node.style?.border || "#253a56")} maskColor="rgba(3,7,18,0.65)"/></ReactFlow></div><div className="graph-legend"><span><i className="legend-node"/> Architecture block</span><span><i className="legend-edge"/> Detected or inferred flow</span><span>Click a block to inspect one representative file</span></div></section>}
          <section className="panel ask-panel" id="ask"><div className="panel-heading"><div><h3><BrainCircuit size={18}/> Ask your codebase</h3><p>Ask a question and get file-grounded guidance.</p></div><span className="local-tag"><span className="tiny-dot"/> LOCAL MODEL</span></div><form className="ask-form" onSubmit={ask}><input value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Where does authentication happen?" required/><button className="primary-button" disabled={asking}>{asking?<LoaderCircle className="spin" size={16}/>:<><Sparkles size={15}/> Ask CodeSloth</>}</button></form><div className="suggestions"><button onClick={()=>setQuestion("Where is authentication implemented?")}>Where is authentication?</button><button onClick={()=>setQuestion("What are the main application entry points?")}>Main entry points?</button><button onClick={()=>setQuestion("How does the application persist data?")}>How is data persisted?</button></div>{answer&&<div className="answer-box"><div className="answer-meta"><span><BrainCircuit size={15}/> {answer.mode==="ollama"?"Ollama response":"Index fallback"}</span><span>{answer.evidence.length} evidence files</span></div><div className="answer-text">{answer.answer}</div><h4>Evidence used</h4><div className="evidence-list">{answer.evidence.map(e=><button key={e.path} onClick={()=>selectFile(e.path)}><FileCode2 size={14}/><span>{e.path}</span><small>{e.symbols.length} symbols</small></button>)}</div></div>}</section>
          <div className="footer-note"><ShieldCheck size={14}/> Source is not executed. Verify AI explanations against the linked code.</div>
        </>}
      </div>
    </section>
  </main>;
}
