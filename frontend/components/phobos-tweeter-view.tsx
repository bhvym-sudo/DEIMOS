"use client";

import { Activity, CalendarDays, ExternalLink, Radio, Search, Send, Square, UserRound } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { twitterApi } from "@/lib/api";
import type { TwitterAccount, TwitterJob, TwitterPost, TwitterScanConfig, TwitterSessionStatus } from "@/lib/types";

export const defaultTwitterConfig: TwitterScanConfig = {
  mode: "keywords", resultMode: "latest", matchMode: "OR", terms: [], accountFilters: [],
  customQuery: "", fromDate: "", toDate: "", maxPosts: 100, scrollDelay: 3,
};

const wait = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export async function executeTwitterScan(config: TwitterScanConfig, onJob?: (job: TwitterJob) => void) {
  const created = await twitterApi.post<{ jobId: string }>("/scan", config);
  while (true) {
    const job = await twitterApi.get<TwitterJob>(`/jobs/${created.jobId}`);
    onJob?.(job);
    if (job.status === "completed") break;
    if (job.status === "failed" || job.status === "cancelled") throw new Error(job.error || job.message);
    await wait(650);
  }
  return twitterApi.get<{ total: number; posts: TwitterPost[] }>("/posts");
}

function accountHandle(post: TwitterPost) {
  return String(post.author?.screen_name || "unknown");
}

function metric(post: TwitterPost, key: string) {
  const value = Number(post.metrics?.[key] || 0);
  return Number.isFinite(value) ? value.toLocaleString() : "0";
}

export function PhobosTweeterView({ sendToWorkspace }: { sendToWorkspace: (post: TwitterPost) => void }) {
  const [config, setConfig] = useState<TwitterScanConfig>(defaultTwitterConfig);
  const [terms, setTerms] = useState("");
  const [filters, setFilters] = useState("");
  const [posts, setPosts] = useState<TwitterPost[]>([]);
  const [job, setJob] = useState<TwitterJob | null>(null);
  const [session, setSession] = useState<TwitterSessionStatus | null>(null);
  const [accountQuery, setAccountQuery] = useState("");
  const [account, setAccount] = useState<TwitterAccount | null>(null);
  const [accountBusy, setAccountBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const stored = window.localStorage.getItem("deimos-phobos-tweeter-config");
    if (stored) {
      try {
        const parsed = { ...defaultTwitterConfig, ...JSON.parse(stored) };
        setConfig(parsed); setTerms(parsed.terms.join(", ")); setFilters(parsed.accountFilters.join(", "));
      } catch { /* Ignore damaged browser preferences. */ }
    }
    void twitterApi.get<TwitterSessionStatus>("/session/status").then(setSession).catch(() => setSession(null));
  }, []);

  const running = job?.status === "queued" || job?.status === "running";
  const effectiveConfig = useMemo(() => ({
    ...config,
    terms: terms.split(",").map((value) => value.trim()).filter(Boolean),
    accountFilters: filters.split(",").map((value) => value.trim()).filter(Boolean),
  }), [config, terms, filters]);

  const saveConfig = () => {
    window.localStorage.setItem("deimos-phobos-tweeter-config", JSON.stringify(effectiveConfig));
    setError("Settings saved in this DEIMOS browser.");
  };

  const scan = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setPosts([]);
    if (effectiveConfig.mode !== "custom" && !effectiveConfig.terms.length) return setError("Enter at least one keyword or account.");
    if (effectiveConfig.mode === "custom" && !effectiveConfig.customQuery.trim()) return setError("Enter a custom X query.");
    try {
      const result = await executeTwitterScan(effectiveConfig, setJob);
      setPosts(result.posts);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "PHOBOS-Tweeter scan failed."); }
  };

  const stop = async () => {
    if (!job?.id) return;
    await twitterApi.delete(`/jobs/${job.id}`).catch(() => undefined);
  };

  const lookup = async (event: FormEvent) => {
    event.preventDefault();
    const screenName = accountQuery.trim().replace(/^@/, "").replace(/^https?:\/\/(?:www\.)?(?:x|twitter)\.com\//i, "").split(/[/?]/)[0];
    if (!screenName) return;
    setAccountBusy(true); setError("");
    try { setAccount(await twitterApi.post<TwitterAccount>("/account", { screenName })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Account lookup failed."); }
    finally { setAccountBusy(false); }
  };

  return <div className="twitter-console">
    <section className="twitter-command">
      <div className="section-title"><div><span>SOCIAL INTELLIGENCE</span><h2>PHOBOS-Tweeter Scan</h2></div><span className={`twitter-session ${session?.ready ? "ready" : ""}`}><Radio size={13} />{session?.ready ? "Session ready" : "Session unavailable"}</span></div>
      <p className="twitter-session-copy">{session?.message || "The private PHOBOS-Tweeter service is offline."}</p>
      <form onSubmit={scan}>
        <label>Search type<select value={config.mode} onChange={(event) => setConfig({ ...config, mode: event.target.value as TwitterScanConfig["mode"] })}><option value="keywords">Keywords</option><option value="accounts">Accounts</option><option value="custom">Custom query</option></select></label>
        <label>Result type<select value={config.resultMode} onChange={(event) => setConfig({ ...config, resultMode: event.target.value as "latest" | "top" })}><option value="latest">Latest</option><option value="top">Top</option></select></label>
        {config.mode !== "custom" ? <>
          <label className="twitter-wide">{config.mode === "accounts" ? "Account usernames" : "Keywords"}<textarea rows={3} value={terms} onChange={(event) => setTerms(event.target.value)} placeholder={config.mode === "accounts" ? "alias_one, alias_two" : "alias, phrase, identifier"} /></label>
          {config.mode === "accounts" && <label className="twitter-wide">Account keyword filters<input value={filters} onChange={(event) => setFilters(event.target.value)} placeholder="Optional comma-separated filters" /></label>}
          {config.mode === "keywords" && <label>Match mode<select value={config.matchMode} onChange={(event) => setConfig({ ...config, matchMode: event.target.value as "OR" | "AND" })}><option value="OR">Any keyword</option><option value="AND">All keywords</option></select></label>}
        </> : <label className="twitter-wide">Custom X query<textarea rows={6} value={config.customQuery} onChange={(event) => setConfig({ ...config, customQuery: event.target.value })} placeholder={'(from:alias OR @alias OR "alias") lang:en'} /></label>}
        <label><CalendarDays size={13} /> From date<input type="date" value={config.fromDate} onChange={(event) => setConfig({ ...config, fromDate: event.target.value })} /></label>
        <label><CalendarDays size={13} /> To date<input type="date" value={config.toDate} onChange={(event) => setConfig({ ...config, toDate: event.target.value })} /></label>
        <label>Maximum posts<input type="number" min={20} max={5000} step={20} value={config.maxPosts} onChange={(event) => setConfig({ ...config, maxPosts: Number(event.target.value) })} /></label>
        <label>Request delay<input type="number" min={1} max={15} value={config.scrollDelay} onChange={(event) => setConfig({ ...config, scrollDelay: Number(event.target.value) })} /></label>
        <div className="twitter-command-actions"><button type="submit" className="primary-action" disabled={running || !session?.ready}><Search size={15} />{running ? "Scanning…" : "Execute scan"}</button><button type="button" className="secondary-action" onClick={stop} disabled={!running}><Square size={13} fill="currentColor" />Stop</button><button type="button" className="secondary-action" onClick={saveConfig}>Save settings</button></div>
      </form>
      <div className="twitter-progress"><i style={{ width: `${job?.progress || 0}%` }} /><span>{job?.message || "Ready"}</span><b>{job?.count || 0}</b></div>
      {error && <p className="twitter-error">{error}</p>}
      <details className="twitter-account-lookup"><summary><UserRound size={14} /> Account Info</summary><form onSubmit={lookup}><input value={accountQuery} onChange={(event) => setAccountQuery(event.target.value)} placeholder="@username" /><button disabled={accountBusy}>{accountBusy ? "Loading…" : "Get account info"}</button></form>{account && <div className="twitter-account-card">{account.avatarUrl && <img src={account.avatarUrl} alt="" />}<div><h3>{account.name}</h3><span>@{account.screenName}</span></div>{account.sections.map((section) => <section key={section.title}><strong>{section.title}</strong>{section.rows.slice(0, 8).map((row) => <p key={row.label}><span>{row.label}</span><b>{String(row.value ?? "")}</b></p>)}</section>)}</div>}</details>
    </section>

    <section className="twitter-results">
      <div className="section-title"><div><span>SCAN RESULTS</span><h2>Extracted X posts</h2></div><span className="count">{posts.length}</span></div>
      <div className="twitter-post-list">{posts.map((post) => <article key={post.id} className="twitter-post-card"><header><div><strong>@{accountHandle(post)}</strong><span>{String(post.author?.name || "")}</span></div><time>{post.createdAt}</time></header><p>{post.text}</p><footer><span>Replies {metric(post, "reply_count")}</span><span>Reposts {metric(post, "retweet_count")}</span><span>Likes {metric(post, "like_count")}</span><span>Views {metric(post, "view_count")}</span><button onClick={() => sendToWorkspace(post)}><Send size={13} /> Workspace</button>{post.url && <a href={post.url} target="_blank" rel="noreferrer"><ExternalLink size={13} /></a>}</footer></article>)}{!posts.length && <div className="empty-state"><Activity size={28} /><strong>No scan results</strong><p>Configure a query and execute a PHOBOS-Tweeter scan.</p></div>}</div>
    </section>
  </div>;
}
