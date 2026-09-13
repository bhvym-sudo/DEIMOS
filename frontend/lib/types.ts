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

export type WorkspaceNodeType = "profile" | "post" | "comment" | "lead" | "website" | "social_account" | "social_post";

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

export interface TwitterSessionStatus {
  ready: boolean;
  screenName?: string;
  hasCookies: boolean;
  hasBearer: boolean;
  lastUpdated?: string;
  message: string;
}

export interface TwitterScanConfig {
  mode: "keywords" | "accounts" | "custom";
  resultMode: "latest" | "top";
  matchMode: "OR" | "AND";
  terms: string[];
  accountFilters: string[];
  customQuery: string;
  fromDate: string;
  toDate: string;
  maxPosts: number;
  scrollDelay: number;
}

export interface TwitterPost {
  id: string;
  conversationId?: string;
  text: string;
  createdAt: string;
  url: string;
  query?: string;
  author: Record<string, unknown> & { screen_name?: string; name?: string; profile_image_url?: string };
  metrics: Record<string, unknown>;
  entities?: Record<string, unknown>;
  media?: unknown[];
  raw?: Record<string, unknown>;
}

export interface TwitterJob {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  message: string;
  count: number;
  error?: string;
}

export interface TwitterAccount {
  screenName: string;
  name: string;
  avatarUrl: string;
  fields: Record<string, unknown>;
  sections: Array<{ title: string; rows: Array<{ label: string; value: unknown }> }>;
  rawProfile?: Record<string, unknown>;
  rawAbout?: Record<string, unknown>;
}

export interface PersonaModelStatus {
  trained: boolean;
  model_path: string;
  calibration?: null | {
    dataset: string; authors: number; training_pairs: number; validation_pairs: number;
    roc_auc: number; accuracy: number; precision: number; recall: number; f1: number;
    brier: number; author_disjoint_validation: boolean;
  };
  run: null | {
    id: number; trained_at: string; profile_count: number; usable_profiles: number;
    activity_count: number; feature_count: number; match_count: number;
    threshold: number; model_version: string;
  };
}

export interface PersonaMatch {
  id: number; left_profile_id: number; right_profile_id: number;
  left_username: string; right_username: string; left_domain: string; right_domain: string;
  left_profile_url: string; right_profile_url: string;
  confidence: number; classification: string; stylometry_similarity: number;
  semantic_similarity: number; behavioral_similarity: number;
  identifier_similarity: number; alias_similarity: number; evidence: string[]; created_at: string;
}
