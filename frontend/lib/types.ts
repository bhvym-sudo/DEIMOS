export type ServiceState = "connecting" | "online" | "offline";

export interface OverviewStats {
  indexed_pages: number;
  queued_pages: number;
  analyzed_pages: number;
  critical_findings: number;
  high_findings: number;
  entities_found: number;
  crawler_running: boolean;
  tor_configured: boolean;
}

export interface StreamEvent {
  type: string;
  source: "go" | "python" | "system";
  message: string;
  timestamp: string;
  level?: "info" | "success" | "warning" | "critical";
  data?: Record<string, unknown>;
}

export interface SearchResult {
  id: number;
  url: string;
  title: string;
  snippet: string;
  domain: string;
  crawled_at: string;
  score: number;
}

export interface DatabasePage {
  id: number; url: string; title: string; domain: string; content?: string; html?: string;
  content_length: number; crawl_depth: number; crawled_at: string; status_code: number; crawl_count: number;
  threat_score: number; threat_level: string; analyzed_at: string; content_type: string; server_banner: string;
  powered_by: string; response_headers: string; tls_subject: string; tls_issuer: string; tls_serial: string;
  tls_not_before: string; tls_not_after: string; tls_dns_names: string; tls_fingerprint_sha256: string;
  status_pages: string; recon_scanned_at: string;
}

export interface ThreatReport {
  id: number;
  page_id: number;
  url: string;
  threat_score: number;
  threat_level: string;
  risk_classification?: string;
  origin_country?: string;
  matched_keywords: string[];
  analyzed_at: string;
}

export interface SeedURL {
  url: string;
  web_type: string;
  added_by?: string;
  remarks?: string;
  timestamp?: string;
}

export interface CrawlerConfig {
  max_depth: number;
  concurrent_crawlers: number;
  download_delay: number;
  use_tor: boolean;
  tor_proxy: string;
  request_timeout_seconds: number;
  max_body_bytes: number;
  user_agent: string;
  database_path: string;
  same_host_only: boolean;
}

export interface CrawlerStatus {
  running: boolean;
  started_at?: string;
  pages_crawled: number;
  request_errors: number;
  active_workers: number;
  indexed_pages: number;
  pending_urls: number;
  failed_urls: number;
}

export interface ProfileRecord {
  id: number;
  profile_url: string;
  source_engine: string;
  source_domain: string;
  username: string;
  display_name: string;
  role: string;
  territory: string;
  joined_at: string;
  last_active: string;
  reputation: string;
  bio: string;
  avatar_url: string;
  contacts: string[];
  pgp_identifiers: string[];
  wallets: string[];
  posts: string[];
  comments: string[];
  ner_entities: Record<string, string[]>;
  profile_text: string;
  raw_html: string;
  detection_method: string;
  detection_confidence: number;
  first_seen: string;
  last_seen: string;
  crawled_at: string;
  observation_count: number;
  history: Array<Record<string, unknown> & { observed_at: string }>;
  activity: ProfileActivity[];
}

export interface ProfileActivity {
  type: "post" | "comment";
  title: string;
  body: string;
  community: string;
  date_label: string;
  source_page_url: string;
  target_url: string;
  page_number: number;
  position: number;
  first_seen: string;
  last_seen: string;
}

export type WorkspaceNodeType = "profile" | "post" | "comment" | "lead" | "website";

export interface WorkspaceNode {
  id: string;
  type: WorkspaceNodeType;
  label: string;
  subtitle: string;
  url: string;
  depth: number;
  side: number;
  known: boolean;
  profile_id?: number;
  metadata: Record<string, unknown>;
}

export interface WorkspaceEdge {
  id: string;
  source: string;
  target: string;
  relationship: string;
}

export interface WorkspaceGraph {
  nodes: WorkspaceNode[];
  edges: WorkspaceEdge[];
  roots: string[];
  crawl_urls: string[];
  depth: number;
  truncated: boolean;
}
