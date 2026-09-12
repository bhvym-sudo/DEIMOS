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
