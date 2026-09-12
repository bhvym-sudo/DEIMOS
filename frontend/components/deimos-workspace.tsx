"use client";

import {
  Activity,
  BrainCircuit,
  ChevronRight,
  Database,
  FileSearch,
  Gauge,
  Globe2,
  Home,
  Network,
  Play,
  Plus,
  Radar,
  Radio,
  RefreshCw,
  Search,
  Server,
  Save,
  Settings2,
  ShieldAlert,
  Square,
  TerminalSquare,
  Trash2,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useServiceSocket } from "@/hooks/use-service-socket";
import { browserServiceUrl, goApi, pythonApi } from "@/lib/api";
import type { CrawlerConfig, DatabasePage, OverviewStats, SearchResult, SeedURL, ServiceState, StreamEvent } from "@/lib/types";

type View = "overview" | "crawl" | "crawler-data" | "search" | "intelligence" | "models" | "system";

const GO_WS = `${browserServiceUrl(process.env.NEXT_PUBLIC_GO_WS_URL, 8787, "ws")}/ws`;
const PYTHON_WS = `${browserServiceUrl(process.env.NEXT_PUBLIC_PYTHON_WS_URL, 8001, "ws")}/ws`;

const emptyStats: OverviewStats = {
  indexed_pages: 0,
  queued_pages: 0,
  analyzed_pages: 0,
  critical_findings: 0,
  high_findings: 0,
  entities_found: 0,
  crawler_running: false,
  tor_configured: false,
};

const defaultCrawlerConfig: CrawlerConfig = {
  max_depth: 3,
  concurrent_crawlers: 10,
  download_delay: 1,
  use_tor: true,
  tor_proxy: "127.0.0.1:9050",
  request_timeout_seconds: 60,
  max_body_bytes: 5242880,
  user_agent: "DEIMOS-Collector/0.2 (+authorized-security-research)",
  database_path: "phobos/databases/phobos_index.db",
  same_host_only: true,
};

const modelRows = [
  { name: "PHOBOS-NER", role: "Cyber entity extraction", stage: "Prototype", health: 62 },
  { name: "ECHO-STYLE", role: "Stylometric persona matching", stage: "Planned", health: 15 },
  { name: "HYDRA-LINK", role: "Cross-platform entity resolution", stage: "Planned", health: 20 },
  { name: "ARGUS-BEHAVIOR", role: "Temporal and behavioral profiling", stage: "Planned", health: 10 },
  { name: "THEMIS-FUSION", role: "Evidence and confidence fusion", stage: "Planned", health: 8 },
];

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-IN").format(value);
}

function formatTime(value?: string) {
  if (!value) return "Unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusLabel(status: string) {
  return status === "online" ? "Connected" : status === "connecting" ? "Connecting" : "Offline";
}

function ServiceIndicator({ label, status }: { label: string; status: string }) {
  return (
    <div className="service-indicator">
      <span className={`status-dot ${status}`} />
      <span>{label}</span>
      <strong>{statusLabel(status)}</strong>
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: "risk" | "signal" }) {
  return (
    <div className={`metric ${accent ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DeimosWorkspace() {
  const [view, setView] = useState<View>("overview");
  const [stats, setStats] = useState<OverviewStats>(emptyStats);
  const [searchStats, setSearchStats] = useState<OverviewStats>(emptyStats);
  const [crawlerPages, setCrawlerPages] = useState<DatabasePage[]>([]);
  const [indexPages, setIndexPages] = useState<DatabasePage[]>([]);
  const [selectedPage, setSelectedPage] = useState<DatabasePage | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [seeds, setSeeds] = useState<SeedURL[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchSettingsOpen, setSearchSettingsOpen] = useState(false);
  const [searchBusy, setSearchBusy] = useState(false);
  const [torStatus, setTorStatus] = useState<ServiceState>("connecting");
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [crawlerBusy, setCrawlerBusy] = useState(false);
  const [settings, setSettings] = useState<CrawlerConfig>(defaultCrawlerConfig);
  const [searchSettings, setSearchSettings] = useState<CrawlerConfig>({ ...defaultCrawlerConfig, database_path: "phobos/databases/phobos_search.db", same_host_only: false, concurrent_crawlers: 20 });
  const [savedSearchSettings, setSavedSearchSettings] = useState<CrawlerConfig | null>(null);
  const [searchSeeds, setSearchSeeds] = useState<SeedURL[]>([]);
  const [seedDraft, setSeedDraft] = useState({ url: "", remarks: "", added_by: "Team Vulkans" });
  const [searchSeedDraft, setSearchSeedDraft] = useState({ url: "", remarks: "", added_by: "Team Vulkans" });

  const goSocket = useServiceSocket(GO_WS, "go");
  const pythonSocket = useServiceSocket(PYTHON_WS, "python");

  const loadData = useCallback(async () => {
    setRefreshing(true);
    const [crawlerData, searchData, crawlerAnalysis, searchAnalysis, crawlerPageData, indexPageData, seedData, searchSeedData, torData] = await Promise.allSettled([
      goApi.get<Partial<OverviewStats>>("/api/crawler/stats"),
      goApi.get<Partial<OverviewStats>>("/api/phobos-search/stats"),
      pythonApi.get<Partial<OverviewStats>>("/api/stats/crawler"),
      pythonApi.get<Partial<OverviewStats>>("/api/stats/phobos-search"),
      goApi.get<{ pages: DatabasePage[] }>("/api/crawler/pages?limit=75"),
      goApi.get<{ pages: DatabasePage[] }>("/api/phobos-search/pages?limit=75"),
      goApi.get<{ seeds: SeedURL[] }>("/api/crawler/seeds"),
      goApi.get<{ seeds: SeedURL[] }>("/api/phobos-search/seeds"),
      goApi.get<{ status: "online" | "offline" }>("/api/tor/health"),
    ]);

    setStats((current) => ({
      ...current,
      ...(crawlerData.status === "fulfilled" ? crawlerData.value : {}),
      ...(crawlerAnalysis.status === "fulfilled" ? crawlerAnalysis.value : {}),
    }));
    setSearchStats((current) => ({ ...current, ...(searchData.status === "fulfilled" ? searchData.value : {}), ...(searchAnalysis.status === "fulfilled" ? searchAnalysis.value : {}) }));
    if (crawlerPageData.status === "fulfilled") setCrawlerPages(crawlerPageData.value.pages);
    if (indexPageData.status === "fulfilled") setIndexPages(indexPageData.value.pages);
    if (seedData.status === "fulfilled") setSeeds(seedData.value.seeds);
    if (searchSeedData.status === "fulfilled") setSearchSeeds(searchSeedData.value.seeds);
    setTorStatus(torData.status === "fulfilled" && torData.value.status === "online" ? "online" : "offline");
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void loadData();
    void goApi.get<CrawlerConfig>("/api/crawler/config").then(setSettings).catch(() => undefined);
    void goApi.get<CrawlerConfig>("/api/phobos-search/config").then((value) => { setSearchSettings(value); setSavedSearchSettings(value); }).catch(() => undefined);
    const interval = setInterval(() => void loadData(), 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    if (!goSocket.events[0]) return;
    const timer = setTimeout(() => void loadData(), 500);
    return () => clearTimeout(timer);
  }, [goSocket.events, loadData]);

  const events = useMemo(() => {
    const combined = [...goSocket.events, ...pythonSocket.events];
    return combined
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, 300);
  }, [goSocket.events, pythonSocket.events]);

  const openDatabasePage = async (engine: "crawler" | "phobos-search", id: number) => {
    setPageLoading(true);
    try { setSelectedPage(await goApi.get<DatabasePage>(`/api/${engine}/pages/${id}`)); }
    catch { setNotice("The selected database record could not be loaded."); }
    finally { setPageLoading(false); }
  };

  const runCrawlerAction = async (action: "start" | "stop") => {
    setCrawlerBusy(true);
    setNotice(null);
    try {
      if (action === "start") {
        await goApi.put("/api/crawler/config", settings);
      }
      const response = await goApi.post<{ message: string }>(`/api/crawler/${action}`);
      setNotice(response.message);
      await loadData();
    } catch {
      setNotice("The Go gateway is offline. Start it to control the crawler.");
    } finally {
      setCrawlerBusy(false);
    }
  };

  const saveCrawlerConfig = async () => {
    setCrawlerBusy(true);
    setNotice(null);
    try {
      const response = await goApi.put<{ message: string; config: CrawlerConfig }>("/api/crawler/config", settings);
      setSettings(response.config);
      setNotice(response.message);
    } catch (error) {
      setNotice(error instanceof Error ? `Configuration was not saved: ${error.message}` : "Configuration was not saved.");
    } finally {
      setCrawlerBusy(false);
    }
  };

  const addSeed = async (event: FormEvent) => {
    event.preventDefault();
    if (!seedDraft.url.trim()) return;
    setCrawlerBusy(true);
    setNotice(null);
    try {
      const response = await goApi.post<{ message: string; seeds: SeedURL[] }>("/api/crawler/seeds", seedDraft);
      setSeeds(response.seeds);
      setSeedDraft({ ...seedDraft, url: "", remarks: "" });
      setNotice(response.message);
    } catch (error) {
      setNotice(error instanceof Error ? `Seed was not added: ${error.message}` : "Seed was not added.");
    } finally {
      setCrawlerBusy(false);
    }
  };

  const deleteSeed = async (url: string) => {
    setCrawlerBusy(true);
    setNotice(null);
    try {
      const response = await goApi.delete<{ message: string; seeds: SeedURL[] }>("/api/crawler/seeds", { url });
      setSeeds(response.seeds);
      setNotice(response.message);
    } catch (error) {
      setNotice(error instanceof Error ? `Seed was not removed: ${error.message}` : "Seed was not removed.");
    } finally {
      setCrawlerBusy(false);
    }
  };

  const runSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setNotice(null);
    try {
      const data = await goApi.get<{ results: SearchResult[] }>(`/api/phobos-search/search?q=${encodeURIComponent(searchQuery)}`);
      setResults(data.results);
      setHasSearched(true);
    } catch {
      setResults([]);
      setNotice("Search is unavailable while the Go gateway is offline.");
    } finally {
      setSearching(false);
    }
  };

  const runSearchEngineAction = async (action: "start" | "stop") => {
    setSearchBusy(true); setNotice(null);
    try {
      const response = await goApi.post<{ message: string }>(`/api/phobos-search/${action}`);
      setNotice(response.message); await loadData();
    } catch (error) { setNotice(error instanceof Error ? error.message : "PHOBOS Search control failed."); }
    finally { setSearchBusy(false); }
  };

  const saveSearchConfig = async () => {
    setSearchBusy(true); setNotice(null);
    try {
      const response = await goApi.put<{ message: string; config: CrawlerConfig }>("/api/phobos-search/config", searchSettings);
      setSearchSettings(response.config); setSavedSearchSettings(response.config); setNotice(response.message);
    } catch (error) { setNotice(error instanceof Error ? `Stop PHOBOS Search before saving: ${error.message}` : "Configuration was not saved."); }
    finally { setSearchBusy(false); }
  };

  const addSearchSeed = async (event: FormEvent) => {
    event.preventDefault(); if (!searchSeedDraft.url.trim()) return; setSearchBusy(true);
    try {
      const response = await goApi.post<{ message: string; seeds: SeedURL[] }>("/api/phobos-search/seeds", searchSeedDraft);
      setSearchSeeds(response.seeds); setSearchSeedDraft({ ...searchSeedDraft, url: "", remarks: "" }); setNotice(response.message);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Search seed was not added."); }
    finally { setSearchBusy(false); }
  };

  const deleteSearchSeed = async (url: string) => {
    setSearchBusy(true);
    try { const response = await goApi.delete<{ message: string; seeds: SeedURL[] }>("/api/phobos-search/seeds", { url }); setSearchSeeds(response.seeds); setNotice(response.message); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Search seed was not removed."); }
    finally { setSearchBusy(false); }
  };

  const navigation: Array<{ id: View; label: string; icon: typeof Gauge }> = [
    { id: "overview", label: "Overview", icon: Gauge },
    { id: "crawl", label: "Crawler", icon: Radar },
    { id: "crawler-data", label: "Crawler Data", icon: Database },
    { id: "search", label: "PHOBOS Search", icon: Search },
    { id: "intelligence", label: "Index Database", icon: FileSearch },
    { id: "models", label: "AI models", icon: BrainCircuit },
    { id: "system", label: "System", icon: Settings2 },
  ];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div><strong>DEIMOS</strong><span>INTELLIGENCE SYSTEM</span></div>
        </div>

        <nav aria-label="Primary navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button key={id} className={view === id ? "active" : ""} onClick={() => { setView(id); setSelectedPage(null); }}>
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-status">
          <p>Service channels</p>
          <ServiceIndicator label="Go gateway" status={goSocket.status} />
          <ServiceIndicator label="Python AI" status={pythonSocket.status} />
          <ServiceIndicator label="Tor network" status={torStatus} />
        </div>
        <div className="operator"><span>VK</span><div><strong>Team Vulkans</strong><small>Local workspace</small></div></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="breadcrumb">DEIMOS / {navigation.find((item) => item.id === view)?.label}</span>
            <h1>{navigation.find((item) => item.id === view)?.label}</h1>
          </div>
          <div className="top-actions">
            <span className={`system-state ${stats.crawler_running ? "live" : ""}`}>
              <Activity size={14} /> {view === "search" ? (searchStats.crawler_running ? "PHOBOS Search active" : "PHOBOS Search idle") : (stats.crawler_running ? "Crawler active" : "Crawler idle")}
            </span>
            <button className="icon-control" onClick={() => void loadData()} aria-label="Refresh data">
              <RefreshCw className={refreshing ? "spin" : ""} size={17} />
            </button>
          </div>
        </header>

        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice(null)}>Dismiss</button></div>}

        <div className="view-stage">
          {view === "overview" && <Overview />}
          {view === "crawl" && (
            <CollectionView
              stats={stats}
              settings={settings}
              setSettings={setSettings}
              seeds={seeds}
              busy={crawlerBusy}
              seedDraft={seedDraft}
              setSeedDraft={setSeedDraft}
              save={() => void saveCrawlerConfig()}
              addSeed={addSeed}
              deleteSeed={(url) => void deleteSeed(url)}
              start={() => void runCrawlerAction("start")}
              stop={() => void runCrawlerAction("stop")}
            />
          )}
          {view === "crawler-data" && <DatabaseView title="Crawler Data" eyebrow="INVESTIGATION DATABASE" pages={crawlerPages} selected={selectedPage} loading={pageLoading} open={(id) => void openDatabasePage("crawler", id)} close={() => setSelectedPage(null)} />}
          {view === "search" && (
            <SearchView query={searchQuery} setQuery={setSearchQuery} submit={runSearch} results={results} searching={searching} hasSearched={hasSearched} home={() => { setHasSearched(false); setResults([]); setSearchQuery(""); }} stats={searchStats} settingsOpen={searchSettingsOpen} setSettingsOpen={setSearchSettingsOpen} settings={searchSettings} setSettings={setSearchSettings} dirty={savedSearchSettings !== null && JSON.stringify(savedSearchSettings) !== JSON.stringify(searchSettings)} busy={searchBusy} save={() => void saveSearchConfig()} start={() => void runSearchEngineAction("start")} stop={() => void runSearchEngineAction("stop")} seeds={searchSeeds} seedDraft={searchSeedDraft} setSeedDraft={setSearchSeedDraft} addSeed={addSearchSeed} deleteSeed={(url) => void deleteSearchSeed(url)} />
          )}
          {view === "intelligence" && <DatabaseView title="PHOBOS Search indexed pages" eyebrow="INDEX DATABASE" pages={indexPages} selected={selectedPage} loading={pageLoading} open={(id) => void openDatabasePage("phobos-search", id)} close={() => setSelectedPage(null)} />}
          {view === "models" && <ModelsView />}
          {view === "system" && <SystemView goStatus={goSocket.status} pythonStatus={pythonSocket.status} torStatus={torStatus} events={events} />}
        </div>
      </section>
    </main>
  );
}

function Overview() {
  return (
    <section className="primary-panel overview-placeholder"><EmptyState icon={Gauge} title="Overview workspace reserved" copy="Crawler investigation summaries, entity resolution and correlation graph signals will be added here in the next phase." /></section>
  );
}

function CollectionView({ stats, settings, setSettings, seeds, busy, seedDraft, setSeedDraft, save, addSeed, deleteSeed, start, stop }: {
  stats: OverviewStats;
  settings: CrawlerConfig;
  setSettings: (value: CrawlerConfig) => void;
  seeds: SeedURL[];
  busy: boolean;
  seedDraft: { url: string; remarks: string; added_by: string };
  setSeedDraft: (value: { url: string; remarks: string; added_by: string }) => void;
  save: () => void;
  addSeed: (event: FormEvent) => void;
  deleteSeed: (url: string) => void;
  start: () => void;
  stop: () => void;
}) {
  return (
    <div className="two-column">
      <section className="control-surface">
        <div className="section-title"><div><span>CRAWLER CONTROL</span><h2>Investigation crawler parameters</h2></div><Radar size={19} /></div>
        <label>Maximum crawl depth<input type="number" min={1} max={8} value={settings.max_depth} onChange={(e) => setSettings({ ...settings, max_depth: Number(e.target.value) })} /></label>
        <label>Concurrent workers<input type="number" min={1} max={50} value={settings.concurrent_crawlers} onChange={(e) => setSettings({ ...settings, concurrent_crawlers: Number(e.target.value) })} /></label>
        <label>Request delay in seconds<input type="number" min={0.5} max={30} step={0.5} value={settings.download_delay} onChange={(e) => setSettings({ ...settings, download_delay: Number(e.target.value) })} /></label>
        <label>Request timeout in seconds<input type="number" min={5} max={300} value={settings.request_timeout_seconds} onChange={(e) => setSettings({ ...settings, request_timeout_seconds: Number(e.target.value) })} /></label>
        <label className="toggle-row"><span><strong>Tor routing</strong><small>Route collection through a SOCKS5 endpoint</small></span><input type="checkbox" checked={settings.use_tor} onChange={(e) => setSettings({ ...settings, use_tor: e.target.checked })} /></label>
        <label>Tor proxy address<input value={settings.tor_proxy} disabled={!settings.use_tor} onChange={(e) => setSettings({ ...settings, tor_proxy: e.target.value })} /></label>
        <label className="toggle-row"><span><strong>Restrict link discovery</strong><small>Only follow links on the same host as the current page</small></span><input type="checkbox" checked={settings.same_host_only} onChange={(e) => setSettings({ ...settings, same_host_only: e.target.checked })} /></label>
        <div className="action-row">
          <button className="primary-action" onClick={start} disabled={busy || stats.crawler_running}><Play size={16} fill="currentColor" /> Start crawler</button>
          <button className="secondary-action" onClick={stop} disabled={busy || !stats.crawler_running}><Square size={15} fill="currentColor" /> Stop</button>
          <button className="secondary-action" onClick={save} disabled={busy || stats.crawler_running}><Save size={15} /> Save</button>
        </div>
      </section>

      <section className="table-panel">
        <div className="section-title"><div><span>SOURCE REGISTRY</span><h2>Seed URLs</h2></div><span className="count">{seeds.length}</span></div>
        <form className="seed-form" onSubmit={addSeed}>
          <input type="url" required placeholder="https://authorized-source.example or http://…onion" value={seedDraft.url} onChange={(event) => setSeedDraft({ ...seedDraft, url: event.target.value })} />
          <input placeholder="Investigation note" value={seedDraft.remarks} onChange={(event) => setSeedDraft({ ...seedDraft, remarks: event.target.value })} />
          <button className="primary-action" type="submit" disabled={busy}><Plus size={15} /> Add source</button>
        </form>
        <div className="table-scroll">
          <table><thead><tr><th>Source</th><th>Network</th><th>Owner</th><th>Added</th><th /></tr></thead>
            <tbody>{seeds.map((seed, index) => <tr key={`${seed.url}-${index}`}><td><Globe2 size={15} /><span>{seed.url}</span><small>{seed.remarks || "No investigation note"}</small></td><td>{seed.web_type.replace("_", " ")}</td><td>{seed.added_by || "System"}</td><td>{seed.timestamp ? formatTime(seed.timestamp) : "Configured"}</td><td><button className="row-action danger" onClick={() => deleteSeed(seed.url)} disabled={busy} aria-label={`Remove ${seed.url}`}><Trash2 size={15} /></button></td></tr>)}</tbody>
          </table>
          {!seeds.length && <EmptyState icon={Globe2} title="No sources loaded" copy="Add an authorized HTTP, HTTPS or onion source to begin collection." />}
        </div>
      </section>
    </div>
  );
}

function SearchView({ query, setQuery, submit, results, searching, hasSearched, home, stats, settingsOpen, setSettingsOpen, settings, setSettings, dirty, busy, save, start, stop, seeds, seedDraft, setSeedDraft, addSeed, deleteSeed }: { query: string; setQuery: (value: string) => void; submit: (event: FormEvent) => void; results: SearchResult[]; searching: boolean; hasSearched: boolean; home: () => void; stats: OverviewStats; settingsOpen: boolean; setSettingsOpen: (value: boolean) => void; settings: CrawlerConfig; setSettings: (value: CrawlerConfig) => void; dirty: boolean; busy: boolean; save: () => void; start: () => void; stop: () => void; seeds: SeedURL[]; seedDraft: { url: string; remarks: string; added_by: string }; setSeedDraft: (value: { url: string; remarks: string; added_by: string }) => void; addSeed: (event: FormEvent) => void; deleteSeed: (url: string) => void }) {
  return (
    <section className="search-surface">
      <div className="search-heading"><div><span>CONTINUOUS DARK-WEB INDEX</span><h2>PHOBOS Search</h2></div><div>{hasSearched && <button className="icon-control" onClick={home} aria-label="PHOBOS Search home"><Home size={17} /></button>}<button className={`icon-control ${settingsOpen ? "active" : ""}`} onClick={() => setSettingsOpen(!settingsOpen)} aria-label="PHOBOS Search settings"><Settings2 size={17} /></button></div></div>
      {settingsOpen && <SearchSettings settings={settings} setSettings={setSettings} stats={stats} dirty={dirty} busy={busy} save={save} start={start} stop={stop} seeds={seeds} seedDraft={seedDraft} setSeedDraft={setSeedDraft} addSeed={addSeed} deleteSeed={deleteSeed} />}
      <form className="search-form" onSubmit={submit}>
        <Search size={20} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search aliases, wallets, domains, keywords or onion URLs" aria-label="Search indexed intelligence" />
        <button type="submit" disabled={searching}>{searching ? "Searching" : "Search index"}</button>
      </form>
      <div className="search-meta"><span>{hasSearched ? `${results.length} results` : "Search the continuously updated PHOBOS index"}</span><span>Evidence remains in the local workspace</span></div>
      {!hasSearched ? <section className="metric-strip search-metrics" aria-label="PHOBOS Search totals"><Metric label="Indexed pages" value={formatNumber(stats.indexed_pages)} /><Metric label="Analysis records" value={formatNumber(stats.analyzed_pages)} /><Metric label="Extracted entities" value={formatNumber(stats.entities_found)} accent="signal" /><Metric label="Critical findings" value={formatNumber(stats.critical_findings)} accent="risk" /></section> : <div className="result-list">
        {results.map((result) => (
          <article key={result.id} className="result-row">
            <div className="result-icon"><FileSearch size={19} /></div>
            <div><span className="result-domain">{result.domain || "Unknown source"}</span><h2>{result.title || result.url}</h2><p>{result.snippet}</p><small>{result.url} · Indexed {formatTime(result.crawled_at)}</small></div>
            <div className="score"><span>Relevance</span><strong>{Math.round(result.score * 100)}%</strong></div>
          </article>
        ))}
        {!results.length && <EmptyState icon={Search} title="No search results" copy="No indexed pages matched this query. Use Home to return to PHOBOS Search statistics." />}
      </div>}
    </section>
  );
}

function SearchSettings({ settings, setSettings, stats, dirty, busy, save, start, stop, seeds, seedDraft, setSeedDraft, addSeed, deleteSeed }: { settings: CrawlerConfig; setSettings: (value: CrawlerConfig) => void; stats: OverviewStats; dirty: boolean; busy: boolean; save: () => void; start: () => void; stop: () => void; seeds: SeedURL[]; seedDraft: { url: string; remarks: string; added_by: string }; setSeedDraft: (value: { url: string; remarks: string; added_by: string }) => void; addSeed: (event: FormEvent) => void; deleteSeed: (url: string) => void }) {
  return <section className="search-settings">
    <div className="section-title"><div><span>PHOBOS SEARCH SETTINGS</span><h2>Continuous indexer configuration {dirty && <em>Unsaved changes</em>}</h2></div><span className={`engine-pill ${stats.crawler_running ? "running" : ""}`}>{stats.crawler_running ? "Running" : "Stopped"}</span></div>
    <div className="settings-grid">
      <label>Maximum crawl depth<input type="number" min={0} max={12} value={settings.max_depth} onChange={(e) => setSettings({ ...settings, max_depth: Number(e.target.value) })} /></label>
      <label>Concurrent workers<input type="number" min={1} max={50} value={settings.concurrent_crawlers} onChange={(e) => setSettings({ ...settings, concurrent_crawlers: Number(e.target.value) })} /></label>
      <label>Request delay (seconds)<input type="number" min={0} max={60} step={0.5} value={settings.download_delay} onChange={(e) => setSettings({ ...settings, download_delay: Number(e.target.value) })} /></label>
      <label>Request timeout (seconds)<input type="number" min={5} max={300} value={settings.request_timeout_seconds} onChange={(e) => setSettings({ ...settings, request_timeout_seconds: Number(e.target.value) })} /></label>
      <label>Tor proxy<input value={settings.tor_proxy} disabled={!settings.use_tor} onChange={(e) => setSettings({ ...settings, tor_proxy: e.target.value })} /></label>
      <label>User agent<input value={settings.user_agent} onChange={(e) => setSettings({ ...settings, user_agent: e.target.value })} /></label>
      <label className="toggle-row"><span><strong>Tor routing</strong><small>Use the configured SOCKS5 endpoint</small></span><input type="checkbox" checked={settings.use_tor} onChange={(e) => setSettings({ ...settings, use_tor: e.target.checked })} /></label>
      <label className="toggle-row"><span><strong>Same-host discovery</strong><small>Limit discovered links to their source host</small></span><input type="checkbox" checked={settings.same_host_only} onChange={(e) => setSettings({ ...settings, same_host_only: e.target.checked })} /></label>
    </div>
    <div className="action-row"><button className="primary-action" onClick={start} disabled={busy || stats.crawler_running}><Play size={15} /> Start</button><button className="secondary-action" onClick={stop} disabled={busy || !stats.crawler_running}><Square size={14} /> Stop</button><button className="secondary-action" onClick={save} disabled={busy || stats.crawler_running || !dirty}><Save size={15} /> Save changes</button></div>
    <div className="settings-seeds"><div className="section-title"><div><span>DISCOVERY SOURCES</span><h2>PHOBOS Search seeds</h2></div><span className="count">{seeds.length}</span></div><form className="seed-form" onSubmit={addSeed}><input type="url" required placeholder="https://source.example or http://…onion" value={seedDraft.url} onChange={(e) => setSeedDraft({ ...seedDraft, url: e.target.value })} /><input placeholder="Source note" value={seedDraft.remarks} onChange={(e) => setSeedDraft({ ...seedDraft, remarks: e.target.value })} /><button className="primary-action" disabled={busy}><Plus size={15} /> Add</button></form><div className="mini-seed-list">{seeds.map((seed) => <div key={seed.url}><span><strong>{seed.url}</strong><small>{seed.remarks || seed.web_type}</small></span><button className="row-action danger" onClick={() => deleteSeed(seed.url)} disabled={busy}><Trash2 size={14} /></button></div>)}</div></div>
  </section>;
}

function DatabaseView({ title, eyebrow, pages, selected, loading, open, close }: { title: string; eyebrow: string; pages: DatabasePage[]; selected: DatabasePage | null; loading: boolean; open: (id: number) => void; close: () => void }) {
  const parsed = (value: string) => { try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value || "—"; } };
  return <div className={`database-layout ${selected ? "detail-open" : ""}`}>
    <section className="table-panel database-browser"><div className="section-title"><div><span>{eyebrow}</span><h2>{title}</h2></div><span className="count">Latest {pages.length}</span></div>
      <div className="table-scroll"><table><thead><tr><th>URL / title</th><th>HTTP</th><th>Server</th><th>Rating</th><th>Crawled</th><th /></tr></thead><tbody>{pages.map((page) => <tr key={page.id} className={selected?.id === page.id ? "selected" : ""}><td><strong className="full-url">{page.url}</strong><small>{page.title || page.domain || "Untitled page"}</small></td><td>{page.status_code || "—"}<small>{page.content_type || "Unknown type"}</small></td><td>{page.server_banner || "—"}<small>{page.powered_by || "No framework banner"}</small></td><td><span className={`severity ${page.threat_level.toLowerCase()}`}>{page.threat_level || "Pending"}</span><small>{Math.round((page.threat_score || 0) * 100)}%</small></td><td>{formatTime(page.crawled_at)}</td><td><button className="row-action" onClick={() => open(page.id)} aria-label={`Open ${page.url}`}><ChevronRight size={17} /></button></td></tr>)}</tbody></table>{!pages.length && <EmptyState icon={Database} title="No pages stored" copy="Start this engine and add a valid seed to populate its database." />}</div>
    </section>
    {selected && <aside className="record-detail"><div className="section-title"><div><span>PAGE RECORD #{selected.id}</span><h2>{selected.title || selected.domain}</h2></div><button className="row-action" onClick={close}>Close</button></div>{loading ? <p className="detail-loading">Loading record…</p> : <div className="detail-content">
      <Detail label="Full URL" value={selected.url} /><div className="detail-grid"><Detail label="HTTP status" value={String(selected.status_code)} /><Detail label="Content size" value={`${formatNumber(selected.content_length)} bytes`} /><Detail label="Crawl depth" value={String(selected.crawl_depth)} /><Detail label="Crawl count" value={String(selected.crawl_count)} /><Detail label="Threat level" value={selected.threat_level || "Pending"} /><Detail label="Threat score" value={`${Math.round((selected.threat_score || 0) * 100)}%`} /></div>
      <h3>Recon intelligence</h3><Detail label="Server banner" value={selected.server_banner || "Not exposed"} /><Detail label="Powered by" value={selected.powered_by || "Not exposed"} /><Detail label="TLS subject" value={selected.tls_subject || "No TLS certificate captured"} /><Detail label="TLS issuer" value={selected.tls_issuer || "—"} /><Detail label="TLS SHA-256 fingerprint" value={selected.tls_fingerprint_sha256 || "—"} /><Detail label="TLS validity" value={selected.tls_not_before ? `${formatTime(selected.tls_not_before)} → ${formatTime(selected.tls_not_after)}` : "—"} /><Detail label="Status pages" value={parsed(selected.status_pages)} code /> <Detail label="Response headers" value={parsed(selected.response_headers)} code />
      <h3>Extracted page content</h3><Detail label="Text" value={selected.content || "No text extracted"} code /><details><summary>Raw HTML</summary><pre>{selected.html || "Raw HTML unavailable"}</pre></details>
    </div>}</aside>}
  </div>;
}

function Detail({ label, value, code = false }: { label: string; value: string; code?: boolean }) { return <div className={`detail-field ${code ? "code" : ""}`}><span>{label}</span><p>{value}</p></div>; }

function ModelsView() {
  return (
    <div className="models-layout">
      <section className="model-intro"><BrainCircuit size={28} /><span>MODEL PIPELINE</span><h2>Specialized intelligence models</h2><p>Each model contributes independent evidence. THEMIS combines those signals into a reviewable confidence score.</p></section>
      <section className="model-list">{modelRows.map((model, index) => <article key={model.name}><span className="model-index">0{index + 1}</span><div><h3>{model.name}</h3><p>{model.role}</p></div><span className={`stage ${model.stage.toLowerCase()}`}>{model.stage}</span><div className="model-progress"><span><i style={{ width: `${model.health}%` }} /></span><small>{model.health}%</small></div></article>)}</section>
    </div>
  );
}

function SystemView({ goStatus, pythonStatus, torStatus, events }: { goStatus: string; pythonStatus: string; torStatus: string; events: StreamEvent[] }) {
  const [sourceFilter, setSourceFilter] = useState<"all" | "crawler" | "phobos-search" | "python">("all");
  const filteredEvents = events.filter((event) => {
    if (sourceFilter === "all") return true;
    if (sourceFilter === "python") return event.source === "python";
    const engine = String(event.data?.engine ?? "").toLowerCase().replace(" ", "-");
    return event.source === "go" && engine === sourceFilter;
  });
  const logText = filteredEvents.length
    ? filteredEvents.map((event) => `[${formatTime(event.timestamp)}] [${event.source.toUpperCase()}] [${event.level?.toUpperCase() ?? "INFO"}] ${event.type} :: ${event.message}`).join("\n")
    : "No live events received for this source.";
  return (
    <div className="two-column system-layout">
      <section className="service-panel"><div className="section-title"><div><span>SERVICE HEALTH</span><h2>Runtime connections</h2></div><Server size={19} /></div>
        <div className="service-card"><Database size={20} /><div><strong>Go gateway</strong><small>REST commands, crawler control and index search</small></div><ServiceIndicator label="Port 8787" status={goStatus} /></div>
        <div className="service-card"><BrainCircuit size={20} /><div><strong>Python intelligence</strong><small>NER, threat analysis, profiles and reports</small></div><ServiceIndicator label="Port 8001" status={pythonStatus} /></div>
        <div className="service-card"><Network size={20} /><div><strong>Tor network</strong><small>SOCKS5 routing for onion-service collection</small></div><ServiceIndicator label="Port 9050" status={torStatus} /></div>
      </section>
      <section className="terminal-panel">
        <div className="section-title"><div><span>EVENT JOURNAL</span><h2>Live service and PHOBOS Search logs</h2></div><TerminalSquare size={19} /></div>
        <div className="terminal-toolbar"><span>{filteredEvents.length} entries</span><label>Source<select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as "all" | "crawler" | "phobos-search" | "python")}><option value="all">All services</option><option value="crawler">Crawler</option><option value="phobos-search">PHOBOS Search</option><option value="python">Python analysis</option></select></label></div>
        <textarea className="terminal-output" value={logText} readOnly spellCheck={false} aria-label="Read-only DEIMOS service logs" />
      </section>
    </div>
  );
}

function EmptyState({ icon: Icon, title, copy }: { icon: typeof Search; title: string; copy: string }) {
  return <div className="empty-state"><Icon size={24} /><strong>{title}</strong><p>{copy}</p></div>;
}
