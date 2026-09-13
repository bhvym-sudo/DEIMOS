"use client";

import { AtSign, ChevronDown, ChevronRight, Crosshair, FileText, GitBranch, Globe2, MessageSquare, Play, Radio, Radar, Save, Search, Settings2, Square, Trash2, UserRound } from "lucide-react";
import { MouseEvent as ReactMouseEvent, useEffect, useMemo, useState } from "react";
import type { CrawlerConfig, OverviewStats, ProfileRecord, TwitterScanConfig, WorkspaceGraph, WorkspaceNode } from "@/lib/types";

const nodeIcon = (type: WorkspaceNode["type"]) => type === "profile" || type === "lead" ? UserRound : type === "social_account" ? AtSign : type === "social_post" ? Radio : type === "post" ? FileText : type === "comment" ? MessageSquare : Globe2;
const nodeOrder: Record<WorkspaceNode["type"], number> = { profile: 0, social_account: 1, website: 2, post: 3, social_post: 4, comment: 5, lead: 6 };

type ContextMenu = { node: WorkspaceNode; x: number; y: number } | null;

function TreeBranch({ node, relationship, root, childrenById, nodesById, collapsed, selected, toggle, select, openMenu, path = new Set() }: {
  node: WorkspaceNode;
  relationship?: string;
  root?: boolean;
  childrenById: Map<string, Array<{ id: string; relationship: string }>>;
  nodesById: Map<string, WorkspaceNode>;
  collapsed: Set<string>;
  selected: WorkspaceNode | null;
  toggle: (id: string) => void;
  select: (node: WorkspaceNode) => void;
  openMenu: (event: ReactMouseEvent, node: WorkspaceNode) => void;
  path?: Set<string>;
}) {
  const cycle = path.has(node.id);
  const children = cycle ? [] : (childrenById.get(node.id) || [])
    .filter((child) => nodesById.has(child.id))
    .sort((a, b) => nodeOrder[nodesById.get(a.id)!.type] - nodeOrder[nodesById.get(b.id)!.type]);
  const closed = collapsed.has(node.id);
  const Icon = nodeIcon(node.type);
  const nextPath = new Set(path); nextPath.add(node.id);
  return <li className={`tree-branch ${root ? "root" : ""}`}>
    <div className={`tree-node ${node.type} ${selected?.id === node.id ? "selected" : ""}`} onClick={() => children.length ? toggle(node.id) : select(node)} onContextMenu={(event) => openMenu(event, node)}>
      <button className="tree-toggle" onClick={(event) => { event.stopPropagation(); toggle(node.id); }} disabled={!children.length} aria-label={closed ? "Expand branch" : "Collapse branch"}>{children.length ? (closed ? <ChevronRight size={16} /> : <ChevronDown size={16} />) : <span />}</button>
      <span className="tree-node-icon"><Icon size={root ? 20 : 15} /></span>
      <div className="tree-node-copy"><div><strong>{node.label}</strong>{relationship && <em>{relationship}</em>}{!node.known && <i>PENDING CRAWL</i>}</div><span>{node.subtitle || node.type}</span></div>
      <small>{children.length ? `${children.length} linked` : node.type}</small>
    </div>
    {!!children.length && !closed && <ul>{children.map((child) => <TreeBranch key={`${node.id}-${child.id}-${child.relationship}`} node={nodesById.get(child.id)!} relationship={child.relationship} childrenById={childrenById} nodesById={nodesById} collapsed={collapsed} selected={selected} toggle={toggle} select={select} openMenu={openMenu} path={nextPath} />)}</ul>}
  </li>;
}

export function InvestigationWorkspace({ graph, roots, depth, maxActivities, pageUrl, autoCrawl, busy, crawlerStats, crawlerConfig, twitterConfig, setTwitterConfig, setCrawlerConfig, saveCrawlerConfig, startCrawler, stopCrawler, setDepth, setMaxActivities, setPageUrl, setAutoCrawl, run, removeRoot, clear, analyzeNode, crawlNode }: {
  graph: WorkspaceGraph;
  roots: ProfileRecord[];
  depth: number;
  maxActivities: number;
  pageUrl: string;
  autoCrawl: boolean;
  busy: boolean;
  crawlerStats: OverviewStats;
  crawlerConfig: CrawlerConfig;
  twitterConfig: TwitterScanConfig;
  setTwitterConfig: (value: TwitterScanConfig) => void;
  setCrawlerConfig: (value: CrawlerConfig) => void;
  saveCrawlerConfig: () => void;
  startCrawler: () => void;
  stopCrawler: () => void;
  setDepth: (value: number) => void;
  setMaxActivities: (value: number) => void;
  setPageUrl: (value: string) => void;
  setAutoCrawl: (value: boolean) => void;
  run: () => void;
  removeRoot: (id: number) => void;
  clear: () => void;
  analyzeNode: (node: WorkspaceNode) => void;
  crawlNode: (node: WorkspaceNode) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<WorkspaceNode | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenu>(null);
  const nodesById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const childrenById = useMemo(() => {
    const result = new Map<string, Array<{ id: string; relationship: string }>>();
    const claimed = new Set(graph.roots);
    graph.edges.forEach((edge) => {
      if (claimed.has(edge.target)) return;
      claimed.add(edge.target);
      result.set(edge.source, [...(result.get(edge.source) || []), { id: edge.target, relationship: edge.relationship }]);
    });
    return result;
  }, [graph.edges, graph.roots]);

  useEffect(() => {
    const compact = new Set<string>();
    const roots = new Set(graph.roots);
    graph.nodes.forEach((node) => { if (!roots.has(node.id) && childrenById.has(node.id)) compact.add(node.id); });
    setCollapsed(compact); setSelected(null); setContextMenu(null);
  }, [graph, childrenById]);
  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener("click", close); window.addEventListener("blur", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); };
  }, []);

  const toggle = (id: string) => setCollapsed((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const openMenu = (event: ReactMouseEvent, node: WorkspaceNode) => { event.preventDefault(); event.stopPropagation(); setSelected(node); setContextMenu({ node, x: event.clientX, y: event.clientY }); };
  const visibleRoots = graph.roots.map((id) => nodesById.get(id)).filter((node): node is WorkspaceNode => Boolean(node));

  return <div className="investigation-workspace">
    <section className="workspace-controls">
      <div className="workspace-control-title"><div><span>LIVE LINK ANALYSIS</span><h2>Investigation Workspace</h2></div><button className="primary-action" onClick={run} disabled={busy || (!roots.length && !pageUrl.trim())}><Play size={15} fill="currentColor" /> {busy ? "Linking…" : "Run link analysis"}</button></div>
      <div className="workspace-control-grid">
        <label>Relationship depth<select value={depth} onChange={(event) => setDepth(Number(event.target.value))}><option value={1}>1 — Direct activity</option><option value={2}>2 — Participants</option><option value={3}>3 — Extended network</option><option value={4}>4 — Deep expansion</option></select></label>
        <label>Activities per profile<input type="number" min={2} max={30} value={maxActivities} onChange={(event) => setMaxActivities(Number(event.target.value))} /></label>
        <label className="workspace-url">Import indexed website<input value={pageUrl} onChange={(event) => setPageUrl(event.target.value)} placeholder="Paste a URL already present in Crawler or PHOBOS Search" /></label>
        <label className="workspace-toggle"><input type="checkbox" checked={autoCrawl} onChange={(event) => setAutoCrawl(event.target.checked)} /><span><strong>Crawl missing profiles</strong><small>Queue discovered profile leads in the crawler</small></span></label>
      </div>
      <div className="workspace-root-row"><span>ROOTS</span>{roots.map((profile) => <button key={profile.id} onClick={() => removeRoot(profile.id)}>@{profile.username || profile.display_name || profile.id} ×</button>)}{!roots.length && <em>No profile roots selected</em>}</div>
      <details className="workspace-crawler-config">
        <summary><span><Settings2 size={15} /><strong>Workspace crawler settings</strong><small>Separate database · one URL at a time</small></span><i className={crawlerStats.crawler_running ? "running" : ""}>{crawlerStats.crawler_running ? "Running" : "Stopped"}</i></summary>
        <div className="workspace-crawler-grid">
          <label>Crawl depth<input type="number" min={0} max={6} value={crawlerConfig.max_depth} disabled={crawlerStats.crawler_running} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, max_depth: Number(event.target.value) })} /></label>
          <label>Request delay (seconds)<input type="number" min={0} max={60} step={.5} value={crawlerConfig.download_delay} disabled={crawlerStats.crawler_running} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, download_delay: Number(event.target.value) })} /></label>
          <label>Timeout (seconds)<input type="number" min={5} max={300} value={crawlerConfig.request_timeout_seconds} disabled={crawlerStats.crawler_running} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, request_timeout_seconds: Number(event.target.value) })} /></label>
          <label>Tor proxy<input value={crawlerConfig.tor_proxy} disabled={crawlerStats.crawler_running || !crawlerConfig.use_tor} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, tor_proxy: event.target.value })} /></label>
          <label className="workspace-crawler-toggle"><input type="checkbox" checked={crawlerConfig.use_tor} disabled={crawlerStats.crawler_running} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, use_tor: event.target.checked })} /> Tor routing</label>
          <label className="workspace-crawler-toggle"><input type="checkbox" checked={crawlerConfig.same_host_only} disabled={crawlerStats.crawler_running} onChange={(event) => setCrawlerConfig({ ...crawlerConfig, same_host_only: event.target.checked })} /> Same-host links only</label>
        </div>
        <div className="workspace-crawler-actions"><span><b>1</b> worker · <b>{crawlerStats.queued_pages}</b> queued · <b>{crawlerStats.indexed_pages}</b> collected</span><div><button onClick={startCrawler} disabled={crawlerStats.crawler_running}><Play size={14} /> Start</button><button onClick={stopCrawler} disabled={!crawlerStats.crawler_running}><Square size={13} fill="currentColor" /> Stop</button><button onClick={saveCrawlerConfig} disabled={crawlerStats.crawler_running}><Save size={14} /> Save settings</button></div></div>
      </details>
      <details className="workspace-crawler-config workspace-twitter-config">
        <summary><span><Radio size={15} /><strong>PHOBOS-Tweeter correlation settings</strong><small>Used by “Analyse with Twitter” from Profiles</small></span><i className="running">Private service</i></summary>
        <div className="workspace-crawler-grid">
          <label>Result type<select value={twitterConfig.resultMode} onChange={(event) => setTwitterConfig({ ...twitterConfig, resultMode: event.target.value as "latest" | "top" })}><option value="latest">Latest</option><option value="top">Top</option></select></label>
          <label>Maximum posts<input type="number" min={20} max={500} step={20} value={twitterConfig.maxPosts} onChange={(event) => setTwitterConfig({ ...twitterConfig, maxPosts: Number(event.target.value) })} /></label>
          <label>Request delay (seconds)<input type="number" min={1} max={15} value={twitterConfig.scrollDelay} onChange={(event) => setTwitterConfig({ ...twitterConfig, scrollDelay: Number(event.target.value) })} /></label>
          <label>From date<input type="date" value={twitterConfig.fromDate} onChange={(event) => setTwitterConfig({ ...twitterConfig, fromDate: event.target.value })} /></label>
          <label>To date<input type="date" value={twitterConfig.toDate} onChange={(event) => setTwitterConfig({ ...twitterConfig, toDate: event.target.value })} /></label>
        </div>
        <div className="workspace-crawler-actions"><span>Searches exact account posts, mentions and alias keywords together</span><div><button onClick={() => window.localStorage.setItem("deimos-phobos-tweeter-workspace-config", JSON.stringify(twitterConfig))}><Save size={14} /> Save settings</button></div></div>
      </details>
    </section>

    <section className="tree-shell">
      <div className="graph-toolbar"><div><GitBranch size={15} /><strong>{graph.nodes.length} nodes</strong><span>{graph.edges.length} links</span>{graph.crawl_urls.length > 0 && <span>{graph.crawl_urls.length} discovery leads</span>}</div><div><button onClick={() => setCollapsed(new Set())} title="Expand all"><ChevronDown size={16} /></button><button onClick={() => setCollapsed(new Set(graph.nodes.filter((node) => childrenById.has(node.id)).map((node) => node.id)))} title="Collapse all"><ChevronRight size={16} /></button><button onClick={clear} title="Clear workspace"><Trash2 size={16} /></button></div></div>
      <div className={`tree-content ${selected ? "with-inspector" : ""}`}>
        <div className="tree-viewport">
          {!visibleRoots.length && <div className="graph-empty"><Crosshair size={30} /><strong>Build an investigation tree</strong><p>Send a profile here or import an indexed website, choose the depth, then run link analysis.</p></div>}
          {!!visibleRoots.length && <ul className="workspace-tree-forest">{visibleRoots.map((node) => <TreeBranch key={node.id} node={node} root childrenById={childrenById} nodesById={nodesById} collapsed={collapsed} selected={selected} toggle={toggle} select={setSelected} openMenu={openMenu} />)}</ul>}
        </div>
        {selected && <aside className="tree-inspector"><button onClick={() => setSelected(null)}>×</button><span>{selected.type.toUpperCase()}</span><h3>{selected.label}</h3><p>{selected.subtitle}</p>{selected.url && <a href={selected.url} target="_blank" rel="noreferrer">{selected.url}</a>}<div className="tree-inspector-actions">{(selected.profile_id || selected.url) && <button onClick={() => analyzeNode(selected)}><Search size={14} /> Analyse beneath node</button>}{selected.url && <button onClick={() => crawlNode(selected)}><Radar size={14} /> Crawl entity</button>}</div><pre>{JSON.stringify(selected.metadata || {}, null, 2)}</pre></aside>}
      </div>
    </section>

    {contextMenu && <div className="entity-context-menu" style={{ left: Math.min(contextMenu.x, window.innerWidth - 230), top: Math.min(contextMenu.y, window.innerHeight - 220) }} onClick={(event) => event.stopPropagation()}>
      <strong>{contextMenu.node.label}</strong>
      <button onClick={() => { toggle(contextMenu.node.id); setContextMenu(null); }}>{collapsed.has(contextMenu.node.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {collapsed.has(contextMenu.node.id) ? "Expand branch" : "Collapse branch"}</button>
      {(contextMenu.node.profile_id || contextMenu.node.url) && <button onClick={() => { analyzeNode(contextMenu.node); setContextMenu(null); }}><Search size={14} /> Analyse beneath node</button>}
      {contextMenu.node.url && <button onClick={() => { crawlNode(contextMenu.node); setContextMenu(null); }}><Radar size={14} /> Crawl / refresh entity</button>}
      <button onClick={() => { setSelected(contextMenu.node); setContextMenu(null); }}><Crosshair size={14} /> Focus details</button>
    </div>}
  </div>;
}
