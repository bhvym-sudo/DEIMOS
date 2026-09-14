"use client";

import {
  Activity,
  BrainCircuit,
  ChevronRight,
  Database,
  FileSearch,
  Gauge,
  GitBranch,
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
  Send,
  Settings2,
  ShieldAlert,
  Square,
  TerminalSquare,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useServiceSocket } from "@/hooks/use-service-socket";
import { InvestigationWorkspace } from "@/components/investigation-workspace";
import { PhobosTweeterView, defaultTwitterConfig, executeTwitterScan } from "@/components/phobos-tweeter-view";
import { browserServiceUrl, goApi, pythonApi, twitterApi } from "@/lib/api";
import type { CrawlerConfig, DatabasePage, OverviewStats, PersonaMatch, PersonaModelStatus, ProfileActivity, ProfileRecord, SearchResult, SeedURL, ServiceState, StreamEvent, TwitterAccount, TwitterPost, TwitterScanConfig, WorkspaceGraph, WorkspaceNode } from "@/lib/types";

type View = "overview" | "workspace" | "crawl" | "crawler-data" | "search" | "intelligence" | "profiles" | "twitter" | "models" | "system";

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

const emptyWorkspaceGraph: WorkspaceGraph = { nodes: [], edges: [], roots: [], crawl_urls: [], depth: 2, truncated: false };

function mergeWorkspaceGraphs(current: WorkspaceGraph, incoming: WorkspaceGraph): WorkspaceGraph {
  const nodes = new Map(current.nodes.map((node) => [node.id, node]));
  const edges = new Map(current.edges.map((edge) => [edge.id, edge]));
  incoming.nodes.forEach((node) => nodes.set(node.id, node));
  incoming.edges.forEach((edge) => edges.set(edge.id, edge));
  return {
    ...incoming,
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    roots: current.roots.length ? current.roots : incoming.roots,
    crawl_urls: [...new Set([...current.crawl_urls, ...incoming.crawl_urls])],
    truncated: current.truncated || incoming.truncated,
  };
}

function twitterWorkspaceGraph(posts: TwitterPost[], account: TwitterAccount | null, parentId = ""): WorkspaceGraph {
  const nodes = new Map<string, WorkspaceNode>();
  const edges = new Map<string, WorkspaceGraph["edges"][number]>();
  const accountMetadata = account ? { ...account.fields, sections: account.sections, source: "PHOBOS-Tweeter account API" } : {};
  for (const post of posts) {
    const handle = String(post.author?.screen_name || account?.screenName || "unknown").replace(/^@/, "");
    const accountId = `twitter:account:${handle.toLowerCase()}`;
    const postId = `twitter:post:${post.id}`;
    if (!nodes.has(accountId)) nodes.set(accountId, {
      id: accountId, type: "social_account", label: `@${handle}`,
      subtitle: String(post.author?.name || account?.name || "X account candidate"),
      url: `https://x.com/${handle}`, depth: parentId ? 1 : 0, side: 1, known: true,
      metadata: { ...accountMetadata, ...post.author, platform: "X", correlation: "alias search" },
    });
    nodes.set(postId, {
      id: postId, type: "social_post", label: post.text.slice(0, 100) || `Post ${post.id}`,
      subtitle: `${handle} · ${formatTime(post.createdAt)}`, url: post.url,
      depth: parentId ? 2 : 1, side: 1, known: true,
      metadata: { platform: "X", query: post.query, metrics: post.metrics, entities: post.entities, text: post.text, created_at: post.createdAt },
    });
    const authoredId = `${accountId}|${postId}|authored`;
    edges.set(authoredId, { id: authoredId, source: accountId, target: postId, relationship: "authored on X" });
    if (parentId) {
      const matchId = `${parentId}|${accountId}|twitter-match`;
      edges.set(matchId, { id: matchId, source: parentId, target: accountId, relationship: "possible X identity" });
    }
  }
  if (account && !posts.length) {
    const accountId = `twitter:account:${account.screenName.toLowerCase()}`;
    nodes.set(accountId, { id: accountId, type: "social_account", label: `@${account.screenName}`, subtitle: account.name || "X account candidate", url: `https://x.com/${account.screenName}`, depth: parentId ? 1 : 0, side: 1, known: true, metadata: accountMetadata });
    if (parentId) edges.set(`${parentId}|${accountId}|twitter-match`, { id: `${parentId}|${accountId}|twitter-match`, source: parentId, target: accountId, relationship: "possible X identity" });
  }
  const accountRoots = [...nodes.values()].filter((node) => node.type === "social_account").map((node) => node.id);
  return { nodes: [...nodes.values()], edges: [...edges.values()], roots: parentId ? [] : accountRoots, crawl_urls: [], depth: 2, truncated: false };
}

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
  { name: "PHOBOS-NER", role: "Cyber entity and identifier extraction", stage: "Active", health: 76 },
  { name: "ECHO-STYLE", role: "Character n-gram stylometric fingerprinting", stage: "Active", health: 72 },
  { name: "HYDRA-LINK", role: "Aliases, wallets, PGP and contact overlap", stage: "Active", health: 68 },
  { name: "ARGUS-BEHAVIOR", role: "Writing activity and behavioural profiling", stage: "Active", health: 66 },
  { name: "THEMIS-FUSION", role: "Explainable confidence-weighted attribution", stage: "Active", health: 74 },
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
  const [profiles, setProfiles] = useState<ProfileRecord[]>([]);
  const [profileCount, setProfileCount] = useState(0);
  const [selectedProfile, setSelectedProfile] = useState<ProfileRecord | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [seeds, setSeeds] = useState<SeedURL[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchSettingsOpen, setSearchSettingsOpen] = useState(false);
  const [searchBusy, setSearchBusy] = useState(false);
  const [torStatus, setTorStatus] = useState<ServiceState>("connecting");
  const [twitterStatus, setTwitterStatus] = useState<ServiceState>("connecting");
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsHeight, setLogsHeight] = useState(300);
  const [workspaceRootIds, setWorkspaceRootIds] = useState<number[]>([]);
  const [workspaceGraph, setWorkspaceGraph] = useState<WorkspaceGraph>(emptyWorkspaceGraph);
  const [workspaceDepth, setWorkspaceDepth] = useState(2);
  const [workspaceMaxActivities, setWorkspaceMaxActivities] = useState(12);
  const [workspacePageUrl, setWorkspacePageUrl] = useState("");
  const [workspaceAutoCrawl, setWorkspaceAutoCrawl] = useState(true);
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [workspaceCrawlerStats, setWorkspaceCrawlerStats] = useState<OverviewStats>(emptyStats);
  const [workspaceCrawlerConfig, setWorkspaceCrawlerConfig] = useState<CrawlerConfig>({ ...defaultCrawlerConfig, max_depth: 1, concurrent_crawlers: 1, database_path: "phobos/databases/workspace.db", user_agent: "DEIMOS-Workspace-Crawler/0.1 (+authorized-security-research)" });
  const [twitterWorkspaceConfig, setTwitterWorkspaceConfig] = useState<TwitterScanConfig>({ ...defaultTwitterConfig, mode: "custom", maxPosts: 40 });
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
    const [crawlerData, searchData, workspaceCrawlerData, crawlerAnalysis, searchAnalysis, crawlerPageData, indexPageData, seedData, searchSeedData, torData, profileData, twitterData] = await Promise.allSettled([
      goApi.get<Partial<OverviewStats>>("/api/crawler/stats"),
      goApi.get<Partial<OverviewStats>>("/api/phobos-search/stats"),
      goApi.get<Partial<OverviewStats>>("/api/workspace-crawler/stats"),
      pythonApi.get<Partial<OverviewStats>>("/api/stats/crawler"),
      pythonApi.get<Partial<OverviewStats>>("/api/stats/phobos-search"),
      goApi.get<{ pages: DatabasePage[] }>("/api/crawler/pages?limit=75"),
      goApi.get<{ pages: DatabasePage[] }>("/api/phobos-search/pages?limit=75"),
      goApi.get<{ seeds: SeedURL[] }>("/api/crawler/seeds"),
      goApi.get<{ seeds: SeedURL[] }>("/api/phobos-search/seeds"),
      goApi.get<{ status: "online" | "offline" }>("/api/tor/health"),
      pythonApi.get<{ profiles: ProfileRecord[]; count: number }>("/api/profiles?limit=100"),
      twitterApi.get<{ ok: boolean }>("/health"),
    ]);

    setStats((current) => ({
      ...current,
      ...(crawlerData.status === "fulfilled" ? crawlerData.value : {}),
      ...(crawlerAnalysis.status === "fulfilled" ? crawlerAnalysis.value : {}),
    }));
    setSearchStats((current) => ({ ...current, ...(searchData.status === "fulfilled" ? searchData.value : {}), ...(searchAnalysis.status === "fulfilled" ? searchAnalysis.value : {}) }));
    setWorkspaceCrawlerStats((current) => ({ ...current, ...(workspaceCrawlerData.status === "fulfilled" ? workspaceCrawlerData.value : {}) }));
    if (crawlerPageData.status === "fulfilled") setCrawlerPages(crawlerPageData.value.pages);
    if (indexPageData.status === "fulfilled") setIndexPages(indexPageData.value.pages);
    if (seedData.status === "fulfilled") setSeeds(seedData.value.seeds);
    if (searchSeedData.status === "fulfilled") setSearchSeeds(searchSeedData.value.seeds);
    if (profileData.status === "fulfilled") {
      setProfiles(profileData.value.profiles);
      setProfileCount(profileData.value.count);
    }
    setTorStatus(torData.status === "fulfilled" && torData.value.status === "online" ? "online" : "offline");
    setTwitterStatus(twitterData.status === "fulfilled" && twitterData.value.ok ? "online" : "offline");
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void loadData();
    void goApi.get<CrawlerConfig>("/api/crawler/config").then(setSettings).catch(() => undefined);
    void goApi.get<CrawlerConfig>("/api/phobos-search/config").then((value) => { setSearchSettings(value); setSavedSearchSettings(value); }).catch(() => undefined);
    void goApi.get<CrawlerConfig>("/api/workspace-crawler/config").then(setWorkspaceCrawlerConfig).catch(() => undefined);
    const storedTwitterWorkspace = window.localStorage.getItem("deimos-phobos-tweeter-workspace-config");
    if (storedTwitterWorkspace) {
      try { setTwitterWorkspaceConfig({ ...defaultTwitterConfig, mode: "custom", ...JSON.parse(storedTwitterWorkspace) }); }
      catch { /* Keep safe defaults when local settings are damaged. */ }
    }
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

  const workspaceRoots = useMemo(() => profiles.filter((profile) => workspaceRootIds.includes(profile.id)), [profiles, workspaceRootIds]);

  const openDatabasePage = async (engine: "crawler" | "phobos-search", id: number) => {
    setPageLoading(true);
    try { setSelectedPage(await goApi.get<DatabasePage>(`/api/${engine}/pages/${id}`)); }
    catch { setNotice("The selected database record could not be loaded."); }
    finally { setPageLoading(false); }
  };

  const openProfile = async (id: number) => {
    setPageLoading(true);
    try { setSelectedProfile(await pythonApi.get<ProfileRecord>("/api/profiles/" + id)); }
    catch { setNotice("The selected profile record could not be loaded."); }
    finally { setPageLoading(false); }
  };

  const runWorkspaceAnalysis = async (profileIds: number[] = workspaceRootIds) => {
    if (!profileIds.length && !workspacePageUrl.trim()) {
      setNotice("Send a profile to Workspace or provide an indexed website URL first.");
      return;
    }
    setWorkspaceBusy(true);
    try {
      const graph = await pythonApi.post<WorkspaceGraph>("/api/workspace/analyze", {
        profile_ids: profileIds,
        page_url: workspacePageUrl.trim(),
        depth: workspaceDepth,
        max_activities: workspaceMaxActivities,
      });
      setWorkspaceGraph(graph);
      let queued = 0;
      if (workspaceAutoCrawl && graph.crawl_urls.length) {
        const results = await Promise.allSettled(graph.crawl_urls.map((url) => goApi.post("/api/workspace-crawler/queue", { url, discovered_from: "workspace-link-analysis" })));
        queued = results.filter((result) => result.status === "fulfilled").length;
        if (queued && !workspaceCrawlerStats.crawler_running) await goApi.post("/api/workspace-crawler/start").catch(() => undefined);
      }
      setNotice(`Workspace generated ${graph.nodes.length} nodes and ${graph.edges.length} links${queued ? `; ${queued} missing profiles queued for crawling` : ""}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Workspace analysis failed.");
    } finally {
      setWorkspaceBusy(false);
    }
  };

  const sendProfileToWorkspace = (profile: ProfileRecord) => {
    const nextRoots = workspaceRootIds.includes(profile.id) ? workspaceRootIds : [...workspaceRootIds, profile.id];
    setWorkspaceRootIds(nextRoots);
    setView("workspace");
    setSelectedProfile(null);
    void runWorkspaceAnalysis(nextRoots);
  };

  const sendTwitterPostToWorkspace = (post: TwitterPost) => {
    const graph = twitterWorkspaceGraph([post], null);
    setWorkspaceGraph((current) => current.nodes.length ? mergeWorkspaceGraphs(current, graph) : graph);
    setView("workspace");
    setNotice("X post and author sent to Workspace.");
  };

  const analyzeProfileWithTwitter = async (profile: ProfileRecord) => {
    const alias = (profile.username || profile.display_name || "").trim().replace(/^@/, "");
    if (!alias) return setNotice("This profile has no alias to search on X.");
    const nextRoots = workspaceRootIds.includes(profile.id) ? workspaceRootIds : [...workspaceRootIds, profile.id];
    setWorkspaceRootIds(nextRoots); setSelectedProfile(null); setView("workspace"); setWorkspaceBusy(true);
    const safeAlias = alias.replace(/["()]/g, "");
    const display = (profile.display_name || "").trim().replace(/["()]/g, "");
    const queryParts = [`from:${safeAlias}`, `@${safeAlias}`, `"${safeAlias}"`];
    if (display && display.toLowerCase() !== safeAlias.toLowerCase()) queryParts.push(`"${display}"`);
    const scanConfig: TwitterScanConfig = { ...twitterWorkspaceConfig, mode: "custom", customQuery: `(${queryParts.join(" OR ")})` };
    try {
      const baseGraph = await pythonApi.post<WorkspaceGraph>("/api/workspace/analyze", { profile_ids: nextRoots, page_url: "", depth: workspaceDepth, max_activities: workspaceMaxActivities });
      const accountPromise = twitterApi.post<TwitterAccount>("/account", { screenName: safeAlias }).catch(() => null);
      const [scan, account] = await Promise.all([executeTwitterScan(scanConfig), accountPromise]);
      const social = twitterWorkspaceGraph(scan.posts, account, `profile:${profile.id}`);
      setWorkspaceGraph(mergeWorkspaceGraphs(baseGraph, social));
      setNotice(`PHOBOS-Tweeter linked ${scan.posts.length} X posts${account ? " and one account candidate" : ""} to @${alias}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Twitter correlation failed.");
    } finally { setWorkspaceBusy(false); }
  };

  const analyzeWorkspaceNode = async (node: WorkspaceNode) => {
    if (!node.profile_id && !node.url) return;
    setWorkspaceBusy(true);
    try {
      const graph = await pythonApi.post<WorkspaceGraph>("/api/workspace/analyze", {
        profile_ids: node.profile_id ? [node.profile_id] : [], page_url: node.profile_id ? "" : node.url,
        depth: Math.min(4, workspaceDepth + 1), max_activities: workspaceMaxActivities,
      });
      const attached = node.profile_id ? graph : { ...graph, edges: [...graph.edges, ...graph.roots.map((root) => ({ id: `${node.id}|${root}|analysed`, source: node.id, target: root, relationship: "analysed" }))] };
      setWorkspaceGraph((current) => mergeWorkspaceGraphs(current, attached));
      setNotice(`Expanded ${node.label} with ${graph.nodes.length} nodes and ${graph.edges.length} links.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Entity analysis failed.");
    } finally {
      setWorkspaceBusy(false);
    }
  };

  const crawlWorkspaceNode = async (node: WorkspaceNode) => {
    if (!node.url) return;
    try {
      await goApi.post("/api/workspace-crawler/queue", { url: node.url, discovered_from: "workspace-entity-action" });
      if (!workspaceCrawlerStats.crawler_running) await goApi.post("/api/workspace-crawler/start").catch(() => undefined);
      setNotice(`${node.label} was queued in the separate one-worker Workspace crawler.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Entity could not be queued for crawling.");
    }
  };

  const saveWorkspaceCrawlerConfig = async () => {
    try {
      const response = await goApi.put<{ message: string; config: CrawlerConfig }>("/api/workspace-crawler/config", { ...workspaceCrawlerConfig, concurrent_crawlers: 1, database_path: "phobos/databases/workspace.db" });
      setWorkspaceCrawlerConfig(response.config); setNotice(response.message);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Workspace crawler settings could not be saved."); }
  };

  const runWorkspaceCrawlerAction = async (action: "start" | "stop") => {
    try {
      const response = await goApi.post<{ message: string }>(`/api/workspace-crawler/${action}`);
      setNotice(response.message); await loadData();
    } catch (error) { setNotice(error instanceof Error ? error.message : `Workspace crawler could not ${action}.`); }
  };

  const removeWorkspaceRoot = (profileId: number) => {
    const nextRoots = workspaceRootIds.filter((id) => id !== profileId);
    setWorkspaceRootIds(nextRoots);
    if (!nextRoots.length && !workspacePageUrl.trim()) setWorkspaceGraph(emptyWorkspaceGraph);
  };

  const clearWorkspace = () => {
    setWorkspaceRootIds([]);
    setWorkspacePageUrl("");
    setWorkspaceGraph(emptyWorkspaceGraph);
  };

  const reanalyzeProfiles = async (engine: "crawler" | "phobos-search") => {
    try {
      const response = await pythonApi.post<{ message: string }>("/api/profiles/reanalyze/" + engine);
      setNotice(response.message + ". The analysis worker will process stored pages in the background.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Profile reanalysis could not be queued.");
    }
  };

  const clearEngineDatabase = async (engine: "crawler" | "phobos-search") => {
    const name = engine === "crawler" ? "Crawler" : "PHOBOS Search";
    if (!window.confirm("Permanently clear all " + name + " pages, queue, and AI analysis records?")) return;
    try {
      const response = await goApi.delete<{ message: string }>("/api/" + engine + "/database", { confirmation: "CLEAR" });
      setNotice(response.message);
      setSelectedPage(null);
      await loadData();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Database could not be cleared.");
    }
  };

  const clearProfileDatabase = async () => {
    if (!window.confirm("Permanently clear every extracted profile and profile scan checkpoint?")) return;
    try {
      const response = await pythonApi.delete<{ message: string }>("/api/profiles?confirmation=CLEAR");
      setNotice(response.message);
      setProfiles([]);
      setProfileCount(0);
      setSelectedProfile(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Profile database could not be cleared.");
    }
  };

  const clearPersonaData = async () => {
    if (!window.confirm("Permanently clear persona fingerprints, attribution hypotheses, and the fitted local persona model?")) return;
    try {
      const response = await pythonApi.delete<{ message: string }>("/api/persona?confirmation=CLEAR");
      setNotice(response.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Persona AI data could not be cleared.");
    }
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
    { id: "workspace", label: "Workspace", icon: GitBranch },
    { id: "crawl", label: "Crawler", icon: Radar },
    { id: "crawler-data", label: "Crawler Data", icon: Database },
    { id: "search", label: "PHOBOS Search", icon: Search },
    { id: "intelligence", label: "Index Database", icon: FileSearch },
    { id: "profiles", label: "Profiles", icon: Network },
    { id: "twitter", label: "PHOBOS-Tweeter", icon: Radio },
    { id: "models", label: "AI models", icon: BrainCircuit },
    { id: "system", label: "System", icon: Settings2 },
  ];

  const beginLogsResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = logsHeight;
    document.body.style.userSelect = "none";
    const resize = (pointerEvent: PointerEvent) => {
      const maximum = Math.max(180, window.innerHeight - 110);
      setLogsHeight(Math.min(maximum, Math.max(150, startHeight + startY - pointerEvent.clientY)));
    };
    const finish = () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", finish);
  };

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
          <ServiceIndicator label="PHOBOS-Tweeter" status={twitterStatus} />
        </div>
        <div className="operator"><span>VK</span><div><strong>DEIMOS</strong><small>Local workspace</small></div></div>
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
            <button className={`icon-control ${logsOpen ? "active" : ""}`} onClick={() => setLogsOpen((open) => !open)} aria-label={logsOpen ? "Close logs panel" : "Open logs panel"} aria-pressed={logsOpen} title="Toggle live logs">
              <TerminalSquare size={17} />
            </button>
            <button className="icon-control" onClick={() => void loadData()} aria-label="Refresh data">
              <RefreshCw className={refreshing ? "spin" : ""} size={17} />
            </button>
          </div>
        </header>

        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice(null)}>Dismiss</button></div>}

        <div className="view-stage">
          {view === "overview" && <Overview crawlerStats={stats} searchStats={searchStats} profileCount={profileCount} />}
          {view === "workspace" && <InvestigationWorkspace graph={workspaceGraph} roots={workspaceRoots} depth={workspaceDepth} maxActivities={workspaceMaxActivities} pageUrl={workspacePageUrl} autoCrawl={workspaceAutoCrawl} busy={workspaceBusy} crawlerStats={workspaceCrawlerStats} crawlerConfig={workspaceCrawlerConfig} twitterConfig={twitterWorkspaceConfig} setTwitterConfig={setTwitterWorkspaceConfig} setCrawlerConfig={setWorkspaceCrawlerConfig} saveCrawlerConfig={() => void saveWorkspaceCrawlerConfig()} startCrawler={() => void runWorkspaceCrawlerAction("start")} stopCrawler={() => void runWorkspaceCrawlerAction("stop")} setDepth={setWorkspaceDepth} setMaxActivities={setWorkspaceMaxActivities} setPageUrl={setWorkspacePageUrl} setAutoCrawl={setWorkspaceAutoCrawl} run={() => void runWorkspaceAnalysis()} removeRoot={removeWorkspaceRoot} clear={clearWorkspace} analyzeNode={(node) => void analyzeWorkspaceNode(node)} crawlNode={(node) => void crawlWorkspaceNode(node)} />}
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
          {view === "crawler-data" && <DatabaseView engine="crawler" title="Crawler Data" eyebrow="INVESTIGATION DATABASE" pages={crawlerPages} selected={selectedPage} loading={pageLoading} open={(id) => void openDatabasePage("crawler", id)} close={() => setSelectedPage(null)} />}
          {view === "search" && (
            <SearchView query={searchQuery} setQuery={setSearchQuery} submit={runSearch} results={results} searching={searching} hasSearched={hasSearched} home={() => { setHasSearched(false); setResults([]); setSearchQuery(""); }} stats={searchStats} settingsOpen={searchSettingsOpen} setSettingsOpen={setSearchSettingsOpen} settings={searchSettings} setSettings={setSearchSettings} dirty={savedSearchSettings !== null && JSON.stringify(savedSearchSettings) !== JSON.stringify(searchSettings)} busy={searchBusy} save={() => void saveSearchConfig()} start={() => void runSearchEngineAction("start")} stop={() => void runSearchEngineAction("stop")} seeds={searchSeeds} seedDraft={searchSeedDraft} setSeedDraft={setSearchSeedDraft} addSeed={addSearchSeed} deleteSeed={(url) => void deleteSearchSeed(url)} />
          )}
          {view === "intelligence" && <DatabaseView engine="phobos-search" title="PHOBOS Search indexed pages" eyebrow="INDEX DATABASE" pages={indexPages} selected={selectedPage} loading={pageLoading} open={(id) => void openDatabasePage("phobos-search", id)} close={() => setSelectedPage(null)} />}
          {view === "profiles" && <ProfilesView profiles={profiles} selected={selectedProfile} loading={pageLoading} open={(id) => void openProfile(id)} close={() => setSelectedProfile(null)} reanalyze={(engine) => void reanalyzeProfiles(engine)} send={sendProfileToWorkspace} twitter={(profile) => void analyzeProfileWithTwitter(profile)} />}
          {view === "twitter" && <PhobosTweeterView sendToWorkspace={sendTwitterPostToWorkspace} />}
          {view === "models" && <ModelsView />}
          {view === "system" && <SystemView goStatus={goSocket.status} pythonStatus={pythonSocket.status} torStatus={torStatus} twitterStatus={twitterStatus} events={events} crawlerStats={stats} searchStats={searchStats} workspaceCrawlerStats={workspaceCrawlerStats} clearDatabase={(engine) => void clearEngineDatabase(engine)} clearProfiles={() => void clearProfileDatabase()} clearPersona={() => void clearPersonaData()} />}
        </div>
      </section>
      {logsOpen && <LogsDock events={events} height={logsHeight} close={() => setLogsOpen(false)} beginResize={beginLogsResize} />}
    </main>
  );
}

type OverviewTrendPoint = { time: number; crawler: number; index: number; analysis: number; profiles: number; critical: number };

function Overview({ crawlerStats, searchStats, profileCount }: { crawlerStats: OverviewStats; searchStats: OverviewStats; profileCount: number }) {
  const [history, setHistory] = useState<OverviewTrendPoint[]>([]);
  useEffect(() => {
    let active = true;
    const loadTimeline = async () => {
      try {
        const result = await pythonApi.get<{ points: Array<Omit<OverviewTrendPoint, "time"> & { time: string }> }>("/api/timeline?bucket=hour&limit=48");
        if (active) setHistory(result.points.map((point) => ({ ...point, time: Date.parse(point.time) })));
      } catch { /* Keep the inventory usable if historical data is unavailable. */ }
    };
    void loadTimeline();
    const interval = window.setInterval(() => void loadTimeline(), 30000);
    return () => { active = false; window.clearInterval(interval); };
  }, []);
  const metrics = [
    { label: "Crawled pages", value: crawlerStats.indexed_pages },
    { label: "Indexed pages", value: searchStats.indexed_pages },
    { label: "Detected profiles", value: profileCount },
    { label: "AI analysis records", value: crawlerStats.analyzed_pages + searchStats.analyzed_pages },
    { label: "Extracted entities", value: crawlerStats.entities_found + searchStats.entities_found },
    { label: "Queued URLs", value: crawlerStats.queued_pages + searchStats.queued_pages },
  ];
  return (
    <section className="overview-summary">
      <div className="overview-heading"><span>INTELLIGENCE INVENTORY</span><h2>DEIMOS at a glance</h2></div>
      <div className="overview-stat-grid">
        {metrics.map((metric) => <article key={metric.label}><span>{metric.label}</span><strong>{formatNumber(metric.value)}</strong></article>)}
      </div>
      <OperationsTrendChart history={history} />
    </section>
  );
}

function OperationsTrendChart({ history }: { history: OverviewTrendPoint[] }) {
  const series = [
    { key: "crawler" as const, label: "Crawler URLs", color: "#d8ff3e" },
    { key: "index" as const, label: "Indexed URLs", color: "#64d9ff" },
    { key: "analysis" as const, label: "AI records", color: "#b48cff" },
    { key: "profiles" as const, label: "Profiles", color: "#f2b84b" },
    { key: "critical" as const, label: "Critical findings", color: "#ff5d5d" },
  ];
  const plotted = history.slice(-30);
  const maximum = Math.max(1, ...plotted.flatMap((point) => series.map((item) => point[item.key])));
  const width = 900, height = 270, left = 48, right = 18, top = 18, bottom = 38;
  const x = (index: number) => left + (index / Math.max(1, plotted.length - 1)) * (width - left - right);
  const y = (value: number) => top + (1 - value / maximum) * (height - top - bottom);
  const path = (key: (typeof series)[number]["key"]) => plotted.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(" ");
  return <section className="overview-trend">
    <div className="overview-trend-head"><div><span>HISTORICAL DATABASE GROWTH</span><h3>URLs and intelligence extracted over time</h3></div><small>Actual stored record totals by timestamp</small></div>
    <div className="overview-legend">{series.map((item) => <span key={item.key}><i style={{ background: item.color }} />{item.label}<b>{formatNumber(plotted.length ? plotted[plotted.length - 1][item.key] : 0)}</b></span>)}</div>
    <div className="overview-chart-wrap"><svg className="overview-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="URLs and intelligence records extracted over time">
      {[0, .25, .5, .75, 1].map((ratio) => <g key={ratio}><line x1={left} y1={y(maximum * ratio)} x2={width - right} y2={y(maximum * ratio)} className="trend-grid" /><text x={left - 8} y={y(maximum * ratio) + 4} textAnchor="end">{Math.round(maximum * ratio)}</text></g>)}
      {series.map((item) => plotted.length > 1 && <path key={item.key} d={path(item.key)} fill="none" stroke={item.color} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />)}
      {series.map((item) => plotted.map((point, index) => <circle key={`${item.key}-${point.time}`} cx={x(index)} cy={y(point[item.key])} r="2.4" fill={item.color} />))}
      <text x={left} y={height - 10}>{plotted[0] ? new Date(plotted[0].time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Waiting"}</text>
      <text x={width - right} y={height - 10} textAnchor="end">{plotted.length ? new Date(plotted[plotted.length - 1].time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "for data"}</text>
    </svg>{plotted.length < 2 && <div className="trend-empty">Collecting timestamped totals. The graph will draw after the next database snapshot.</div>}</div>
  </section>;
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
      {settingsOpen && <SearchSettings close={() => setSettingsOpen(false)} settings={settings} setSettings={setSettings} stats={stats} dirty={dirty} busy={busy} save={save} start={start} stop={stop} seeds={seeds} seedDraft={seedDraft} setSeedDraft={setSeedDraft} addSeed={addSeed} deleteSeed={deleteSeed} />}
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

function SearchSettings({ close, settings, setSettings, stats, dirty, busy, save, start, stop, seeds, seedDraft, setSeedDraft, addSeed, deleteSeed }: { close: () => void; settings: CrawlerConfig; setSettings: (value: CrawlerConfig) => void; stats: OverviewStats; dirty: boolean; busy: boolean; save: () => void; start: () => void; stop: () => void; seeds: SeedURL[]; seedDraft: { url: string; remarks: string; added_by: string }; setSeedDraft: (value: { url: string; remarks: string; added_by: string }) => void; addSeed: (event: FormEvent) => void; deleteSeed: (url: string) => void }) {
  return <div className="settings-overlay" role="presentation" onMouseDown={close}><section className="search-settings settings-dialog" role="dialog" aria-modal="true" aria-label="PHOBOS Search settings" onMouseDown={(event) => event.stopPropagation()}>
    <div className="settings-dialog-head"><div><span>PHOBOS SEARCH</span><h2>Engine settings</h2></div><button className="row-action" onClick={close}>Close</button></div>
    <div className="settings-tab-content">
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
    </div>
  </section></div>;
}

function ProfilesView({ profiles, selected, loading, open, close, reanalyze, send, twitter }: { profiles: ProfileRecord[]; selected: ProfileRecord | null; loading: boolean; open: (id: number) => void; close: () => void; reanalyze: (engine: "crawler" | "phobos-search") => void; send: (profile: ProfileRecord) => void; twitter: (profile: ProfileRecord) => void }) {
  const list = (values?: string[]) => values?.length ? values.join("\n\n") : "—";
  return <div className={"database-layout " + (selected ? "detail-open" : "")}>
    <section className="table-panel database-browser">
      <div className="section-title"><div><span>PROFILE INTELLIGENCE</span><h2>Detected forum and marketplace profiles</h2></div><div className="profile-actions"><span className="count">{profiles.length} profiles</span><button className="secondary-action" onClick={() => reanalyze("crawler")}><RefreshCw size={14} /> Reanalyse Crawler</button><button className="secondary-action" onClick={() => reanalyze("phobos-search")}><RefreshCw size={14} /> Reanalyse Index</button></div></div>
      <div className="table-scroll"><table><thead><tr><th>Identity</th><th>Source</th><th>Role / territory</th><th>Activity</th><th>Confidence</th><th /></tr></thead>
        <tbody>{profiles.map((profile) => <tr key={profile.id} className={selected?.id === profile.id ? "selected" : ""}>
          <td><strong>@{profile.username || "unknown"}</strong><small className="full-url">{profile.profile_url}</small></td>
          <td>{profile.source_domain || "Unknown"}<small>{profile.source_engine}</small></td>
          <td>{profile.role || "Unspecified"}<small>{profile.territory || "No territory"}</small></td>
          <td>{profile.posts.length} posts<small>{profile.comments.length} comments · {profile.observation_count || 1} observations</small></td>
          <td><span className="severity medium">{Math.round(profile.detection_confidence * 100)}%</span><small>{formatTime(profile.last_seen)}</small></td>
          <td><div className="profile-row-actions"><button className="row-action twitter-analyse" onClick={() => twitter(profile)} aria-label={"Analyse " + profile.username + " with Twitter"} title="Analyse with PHOBOS-Tweeter"><Radio size={16} /></button><button className="row-action send-workspace" onClick={() => send(profile)} aria-label={"Send " + profile.username + " to workspace"} title="Send to Workspace"><Send size={16} /></button><button className="row-action" onClick={() => open(profile.id)} aria-label={"Open profile " + profile.username} title="Open profile"><ChevronRight size={17} /></button></div></td>
        </tr>)}</tbody>
      </table>{!profiles.length && <EmptyState icon={Network} title="No profiles detected yet" copy="Profile URLs discovered by either crawler will be classified, extracted and stored here." />}</div>
    </section>
    {selected && <aside className="record-detail"><div className="section-title"><div><span>PROFILE RECORD #{selected.id}</span><h2>@{selected.username || "unknown"}</h2></div><button className="row-action" onClick={close}>Close</button></div>{loading ? <p className="detail-loading">Loading profile…</p> : <div className="detail-content">
      <Detail label="Profile URL" value={selected.profile_url} />
      <div className="detail-grid"><Detail label="Display name" value={selected.display_name || "—"} /><Detail label="Source engine" value={selected.source_engine || "—"} /><Detail label="Role / type" value={selected.role || "—"} /><Detail label="Territory" value={selected.territory || "—"} /><Detail label="Joined" value={selected.joined_at || "—"} /><Detail label="Last active" value={selected.last_active || "—"} /><Detail label="Reputation" value={selected.reputation || "—"} /><Detail label="Detection confidence" value={Math.round(selected.detection_confidence * 100) + "%"} /></div>
      <h3>Identifiers</h3><Detail label="Contacts" value={list(selected.contacts)} code /><Detail label="PGP identifiers" value={list(selected.pgp_identifiers)} code /><Detail label="Cryptocurrency wallets" value={list(selected.wallets)} code /><Detail label="Avatar URL" value={selected.avatar_url || "—"} />
      <ActivityTimeline activity={selected.activity || []} />
      <h3>Entity context</h3><Detail label="NER entities" value={JSON.stringify(selected.ner_entities || {}, null, 2)} code /><Detail label="Detection method" value={selected.detection_method || "—"} /><Detail label="First / last seen" value={formatTime(selected.first_seen) + " → " + formatTime(selected.last_seen)} /><Detail label="Observation history" value={JSON.stringify(selected.history || [], null, 2)} code />
      <h3>Captured profile page</h3><Detail label="Extracted text" value={selected.profile_text || "No profile text extracted"} code /><details><summary>Raw HTML</summary><pre>{selected.raw_html || "Raw HTML unavailable"}</pre></details>
    </div>}</aside>}
  </div>;
}

function ActivityTimeline({ activity }: { activity: ProfileActivity[] }) {
  const section = (type: "post" | "comment", title: string) => {
    const records = activity.filter((item) => item.type === type);
    return <section className="activity-section">
      <div className="activity-heading"><span>{title}</span><strong>{records.length}</strong></div>
      <div className="activity-timeline">{records.map((item, index) => <article className="activity-card" key={item.type + "-" + item.page_number + "-" + item.position + "-" + index}>
        <i className={"timeline-dot " + item.type} />
        <div className="activity-card-head"><span className={"activity-kind " + item.type}>{item.type}</span><time>{item.date_label || "Time unavailable"}</time></div>
        {item.community && <span className="activity-community">{item.community}</span>}
        {item.title && <h4>{item.type === "comment" ? "Comment on: " + item.title : item.title}</h4>}
        {item.body && <p>{item.body}</p>}
        <div className="activity-source"><span>Profile page {item.page_number}</span><span>{item.target_url || item.source_page_url}</span></div>
      </article>)}
      {!records.length && <p className="activity-empty">No {type === "post" ? "posts" : "comments"} extracted from the stored profile pages.</p>}
      </div>
    </section>;
  };
  return <div className="profile-activity"><h3>Activity timeline</h3>{section("post", "Posts")}{section("comment", "Comments")}</div>;
}

type DatabaseFilterState = {
  q: string; threat_level: string; analysis: string; status_code: string;
  content_type: string; recon: string; tls: string; min_score: string;
  max_score: string; date_from: string; date_to: string; sort: string;
  order: string; limit: string;
};

const emptyDatabaseFilters: DatabaseFilterState = {
  q: "", threat_level: "", analysis: "", status_code: "", content_type: "",
  recon: "", tls: "", min_score: "", max_score: "", date_from: "", date_to: "",
  sort: "crawled_at", order: "desc", limit: "50",
};

function DatabaseView({ engine, title, eyebrow, pages: initialPages, selected, loading, open, close }: { engine: "crawler" | "phobos-search"; title: string; eyebrow: string; pages: DatabasePage[]; selected: DatabasePage | null; loading: boolean; open: (id: number) => void; close: () => void }) {
  const [filters, setFilters] = useState<DatabaseFilterState>(emptyDatabaseFilters);
  const [pages, setPages] = useState<DatabasePage[]>(initialPages);
  const [total, setTotal] = useState(initialPages.length);
  const [offset, setOffset] = useState(0);
  const [filtering, setFiltering] = useState(false);
  const [filterError, setFilterError] = useState("");
  const activeFilters = Object.entries(filters).filter(([key, value]) => !["sort", "order", "limit"].includes(key) && value).length;
  const updateFilter = (key: keyof DatabaseFilterState, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setOffset(0);
  };
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setFiltering(true);
      const params = new URLSearchParams({ limit: filters.limit, offset: String(offset), sort: filters.sort, order: filters.order });
      Object.entries(filters).forEach(([key, value]) => {
        if (value && !["limit", "sort", "order"].includes(key)) {
          params.set(key, key === "min_score" || key === "max_score" ? String(Number(value) / 100) : value);
        }
      });
      try {
        const result = await goApi.get<{ pages: DatabasePage[]; total: number }>(`/api/${engine}/pages?${params.toString()}`);
        setPages(result.pages); setTotal(result.total); setFilterError("");
      } catch (error) {
        setFilterError(error instanceof Error ? error.message : "Database query failed");
      } finally { setFiltering(false); }
    }, filters.q ? 350 : 50);
    return () => window.clearTimeout(timer);
  }, [engine, filters, offset]);
  const clearFilters = () => { setFilters(emptyDatabaseFilters); setOffset(0); };
  const parsed = (value: string) => { try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value || "—"; } };
  return <div className={`database-layout ${selected ? "detail-open" : ""}`}>
    <section className="table-panel database-browser"><div className="section-title"><div><span>{eyebrow}</span><h2>{title}</h2></div><span className="count">{filtering ? "Searching..." : `${formatNumber(total)} matching records`}</span></div>
      <div className="database-filter-bar">
        <label className="database-query"><Search size={15} /><input value={filters.q} onChange={(e) => updateFilter("q", e.target.value)} placeholder="Search URL, title, content, domain, server or certificate" /></label>
        <select value={filters.threat_level} onChange={(e) => updateFilter("threat_level", e.target.value)}><option value="">All threat levels</option><option value="CRITICAL">Critical findings</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option><option value="PENDING">Pending rating</option></select>
        <select value={filters.analysis} onChange={(e) => updateFilter("analysis", e.target.value)}><option value="">All analysis states</option><option value="analyzed">AI analysed</option><option value="pending">Awaiting AI</option></select>
        <select value={filters.recon} onChange={(e) => updateFilter("recon", e.target.value)}><option value="">All recon states</option><option value="finding">Recon findings</option><option value="scanned">Recon scanned</option><option value="pending">Recon pending</option></select>
        <select value={filters.tls} onChange={(e) => updateFilter("tls", e.target.value)}><option value="">Any TLS state</option><option value="present">Certificate found</option><option value="absent">No certificate</option></select>
        <input value={filters.status_code} onChange={(e) => updateFilter("status_code", e.target.value.replace(/\D/g, "").slice(0, 3))} placeholder="HTTP code" />
        <select value={filters.content_type} onChange={(e) => updateFilter("content_type", e.target.value)}><option value="">All content types</option><option value="text/html">HTML</option><option value="application/json">JSON</option><option value="text/plain">Plain text</option><option value="application/pdf">PDF</option><option value="image/">Images</option></select>
        <label className="score-filter"><span>Risk %</span><input type="number" min="0" max="100" value={filters.min_score} onChange={(e) => updateFilter("min_score", e.target.value)} placeholder="Min" /><i>-</i><input type="number" min="0" max="100" value={filters.max_score} onChange={(e) => updateFilter("max_score", e.target.value)} placeholder="Max" /></label>
        <label className="date-filter"><span>From</span><input type="date" value={filters.date_from} onChange={(e) => updateFilter("date_from", e.target.value)} /></label>
        <label className="date-filter"><span>To</span><input type="date" value={filters.date_to} onChange={(e) => updateFilter("date_to", e.target.value)} /></label>
        <select value={filters.sort} onChange={(e) => updateFilter("sort", e.target.value)}><option value="crawled_at">Sort: crawl time</option><option value="threat_score">Sort: risk score</option><option value="status_code">Sort: HTTP code</option><option value="content_length">Sort: content size</option><option value="crawl_depth">Sort: crawl depth</option><option value="domain">Sort: domain</option><option value="title">Sort: title</option></select>
        <select value={filters.order} onChange={(e) => updateFilter("order", e.target.value)}><option value="desc">Descending</option><option value="asc">Ascending</option></select>
        <button className="secondary-action filter-reset" onClick={clearFilters} disabled={!activeFilters}><X size={14} /> Clear {activeFilters ? `(${activeFilters})` : ""}</button>
      </div>
      {filterError && <div className="database-filter-error">{filterError}</div>}
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
  const [status, setStatus] = useState<PersonaModelStatus | null>(null);
  const [matches, setMatches] = useState<PersonaMatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [threshold, setThreshold] = useState(0.55);
  const load = useCallback(async () => {
    try {
      const [nextStatus, result] = await Promise.all([
        pythonApi.get<PersonaModelStatus>("/api/persona/status"),
        pythonApi.get<{ matches: PersonaMatch[] }>("/api/persona/matches?limit=100"),
      ]);
      setStatus(nextStatus); setMatches(result.matches); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Persona intelligence is unavailable"); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const train = async () => {
    setBusy(true); setError("");
    try {
      await pythonApi.post<PersonaModelStatus>("/api/persona/train", { threshold, max_matches: 750 });
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Model training failed"); }
    finally { setBusy(false); }
  };
  const run = status?.run;
  return (
    <div className="persona-page">
      <div className="models-layout">
        <section className="model-intro"><BrainCircuit size={28} /><span>PERSONA INTELLIGENCE</span><h2>Explainable multi-model attribution</h2><p>Models analyse posts, comments, writing habits, topics and identifiers. Every result is an attribution hypothesis requiring investigator review.</p></section>
        <section className="model-list">{modelRows.map((model, index) => <article key={model.name}><span className="model-index">0{index + 1}</span><div><h3>{model.name}</h3><p>{model.role}</p></div><span className={`stage ${model.stage.toLowerCase()}`}>{model.stage}</span><div className="model-progress"><span><i style={{ width: `${model.health}%` }} /></span><small>{model.health}%</small></div></article>)}</section>
      </div>
      <section className="persona-control">
        <div className="section-title"><div><span>TRAINING CONTROL</span><h2>THEMIS persona-linking ensemble</h2></div><div className="persona-actions"><label>Minimum confidence<input type="number" min="0.25" max="0.95" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /></label><button className="primary-action" disabled={busy} onClick={() => void train()}><Play size={15} />{busy ? "Training models…" : "Train & analyse profiles"}</button></div></div>
        {error && <div className="persona-error">{error}</div>}
        <div className="persona-metrics"><Metric label="Training profiles" value={formatNumber(run?.usable_profiles || 0)} /><Metric label="Activity samples" value={formatNumber(run?.activity_count || 0)} /><Metric label="Extracted features" value={formatNumber(run?.feature_count || 0)} accent="signal" /><Metric label="Attribution hypotheses" value={formatNumber(run?.match_count || 0)} /></div>
        <div className="persona-model-meta"><span>{status?.trained ? `Model ${run?.model_version} trained ${formatTime(run?.trained_at)}` : "Model not trained"}</span><span>{status?.calibration ? `Evolution validation: AUC ${(status.calibration.roc_auc * 100).toFixed(1)}% · F1 ${(status.calibration.f1 * 100).toFixed(1)}% · ${status.calibration.authors} authors` : "Awaiting Evolution calibration"}</span></div>
      </section>
      <section className="table-panel persona-results">
        <div className="section-title"><div><span>ATTRIBUTION HYPOTHESES</span><h2>Potential rebranded or migrated personas</h2></div><span className="count">Top {matches.length}</span></div>
        <div className="table-scroll"><table><thead><tr><th>Candidate personas</th><th>Confidence</th><th>Model signals</th><th>Explainable evidence</th></tr></thead><tbody>{matches.map((match) => <tr key={match.id}><td><strong>@{match.left_username || match.left_profile_id} ↔ @{match.right_username || match.right_profile_id}</strong><a className="persona-url" href={match.left_profile_url} target="_blank" rel="noreferrer">{match.left_profile_url || "Profile URL unavailable"}</a><a className="persona-url" href={match.right_profile_url} target="_blank" rel="noreferrer">{match.right_profile_url || "Profile URL unavailable"}</a></td><td><span className={`severity ${match.confidence >= .72 ? "high" : "medium"}`}>{Math.round(match.confidence * 100)}%</span><small>{match.classification}</small></td><td><div className="signal-grid"><span>Style <b>{Math.round(match.stylometry_similarity * 100)}%</b></span><span>Topics <b>{Math.round(match.semantic_similarity * 100)}%</b></span><span>Behavior <b>{Math.round(match.behavioral_similarity * 100)}%</b></span><span>Identifiers <b>{Math.round(match.identifier_similarity * 100)}%</b></span></div></td><td><ul className="evidence-list">{match.evidence.slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul></td></tr>)}</tbody></table>{!matches.length && <EmptyState icon={BrainCircuit} title="No attribution hypotheses" copy="Train the models after collecting at least two profiles with sufficient authored posts or comments." />}</div>
      </section>
    </div>
  );
}

function SystemView({ goStatus, pythonStatus, torStatus, twitterStatus, events, crawlerStats, searchStats, workspaceCrawlerStats, clearDatabase, clearProfiles, clearPersona }: { goStatus: string; pythonStatus: string; torStatus: string; twitterStatus: string; events: StreamEvent[]; crawlerStats: OverviewStats; searchStats: OverviewStats; workspaceCrawlerStats: OverviewStats; clearDatabase: (engine: "crawler" | "phobos-search") => void; clearProfiles: () => void; clearPersona: () => void }) {
  const [sourceFilter, setSourceFilter] = useState<"all" | "crawler" | "phobos-search" | "workspace-crawler" | "python">("all");
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
        <div className="service-card"><GitBranch size={20} /><div><strong>Workspace crawler</strong><small>Independent targeted queue with one worker</small></div><ServiceIndicator label="1 worker" status={workspaceCrawlerStats.crawler_running ? "online" : "offline"} /></div>
        <div className="service-card"><Radio size={20} /><div><strong>PHOBOS-Tweeter</strong><small>Private authenticated X search and account intelligence</small></div><ServiceIndicator label="Internal" status={twitterStatus} /></div>
      </section>
      <section className="terminal-panel">
        <div className="section-title"><div><span>EVENT JOURNAL</span><h2>Live service and PHOBOS Search logs</h2></div><TerminalSquare size={19} /></div>
        <div className="terminal-toolbar"><span>{filteredEvents.length} entries</span><label>Source<select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as "all" | "crawler" | "phobos-search" | "workspace-crawler" | "python")}><option value="all">All services</option><option value="crawler">Crawler</option><option value="phobos-search">PHOBOS Search</option><option value="workspace-crawler">Workspace crawler</option><option value="python">Python analysis</option></select></label></div>
        <textarea className="terminal-output" value={logText} readOnly spellCheck={false} aria-label="Read-only DEIMOS service logs" />
      </section>
      <section className="database-admin-panel">
        <div className="section-title"><div><span>SYSTEM STORAGE</span><h2>Database management</h2></div><ShieldAlert size={19} /></div>
        <div className="database-management">
          <div className="database-warning"><ShieldAlert size={18} /><div><strong>Permanent storage actions</strong><span>Stop the relevant engine before clearing data. The schema is preserved, but deleted records cannot be recovered.</span></div></div>
          <article><div><strong>PHOBOS Search database</strong><span>{formatNumber(searchStats.indexed_pages)} indexed pages and associated AI analysis</span></div><button className="danger-action" disabled={searchStats.crawler_running} onClick={() => clearDatabase("phobos-search")}><Trash2 size={15} /> Clear data</button></article>
          <article><div><strong>Crawler database</strong><span>{formatNumber(crawlerStats.indexed_pages)} collected pages and associated AI analysis</span></div><button className="danger-action" disabled={crawlerStats.crawler_running} onClick={() => clearDatabase("crawler")}><Trash2 size={15} /> Clear data</button></article>
          <article><div><strong>Profile intelligence database</strong><span>Extracted identities, profile history, posts, comments and identifiers</span></div><button className="danger-action" onClick={clearProfiles}><Trash2 size={15} /> Clear profiles</button></article>
          <article><div><strong>Persona AI database</strong><span>Stylometric fingerprints, calibrated attribution hypotheses and fitted local model</span></div><button className="danger-action" onClick={clearPersona}><Trash2 size={15} /> Clear AI data</button></article>
        </div>
      </section>
    </div>
  );
}

function LogsDock({ events, height, close, beginResize }: { events: StreamEvent[]; height: number; close: () => void; beginResize: (event: ReactPointerEvent<HTMLDivElement>) => void }) {
  const [sourceFilter, setSourceFilter] = useState<"all" | "crawler" | "phobos-search" | "workspace-crawler" | "python">("all");
  const filteredEvents = events.filter((event) => {
    if (sourceFilter === "all") return true;
    if (sourceFilter === "python") return event.source === "python";
    const engine = String(event.data?.engine ?? "").toLowerCase().replace(" ", "-");
    return event.source === "go" && engine === sourceFilter;
  });
  const logText = filteredEvents.length
    ? filteredEvents.map((event) => `[${formatTime(event.timestamp)}] [${event.source.toUpperCase()}] [${event.level?.toUpperCase() ?? "INFO"}] ${event.type} :: ${event.message}`).join("\n")
    : "No live events received for this source.";
  return <section className="logs-dock" style={{ height }} aria-label="Live DEIMOS logs">
    <div className="logs-resize-handle" onPointerDown={beginResize} title="Drag to resize logs" />
    <header className="logs-dock-header">
      <div><TerminalSquare size={15} /><strong>Logs</strong><span>{filteredEvents.length} entries</span></div>
      <div className="logs-dock-actions">
        <label>Source<select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as "all" | "crawler" | "phobos-search" | "workspace-crawler" | "python")}><option value="all">All services</option><option value="crawler">Crawler</option><option value="phobos-search">PHOBOS Search</option><option value="workspace-crawler">Workspace crawler</option><option value="python">Python analysis</option></select></label>
        <button onClick={close} aria-label="Close logs panel" title="Close logs"><X size={17} /></button>
      </div>
    </header>
    <textarea className="logs-dock-output" value={logText} readOnly spellCheck={false} aria-label="Read-only live service logs" />
  </section>;
}

function EmptyState({ icon: Icon, title, copy }: { icon: typeof Search; title: string; copy: string }) {
  return <div className="empty-state"><Icon size={24} /><strong>{title}</strong><p>{copy}</p></div>;
}
