import scrapy
from scrapy.crawler import CrawlerProcess
from urllib.parse import urljoin, urlparse
import hashlib
import json
import os
from pathlib import Path


class SimpleIntelligenceCrawler(scrapy.Spider):
    name = 'simple_intelligence_crawler'
    
    custom_settings = {
        'DEPTH_LIMIT': 2,
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_DELAY': 1,
        'ROBOTSTXT_OBEY': True,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'LOG_LEVEL': 'INFO',
    }
    
    def __init__(self, seed_urls, analyzer=None, parser=None, storage=None, use_tor=False, *args, **kwargs):
        super(SimpleIntelligenceCrawler, self).__init__(*args, **kwargs)
        self.start_urls = seed_urls
        self.analyzer = analyzer
        self.parser = parser
        self.storage = storage
        self.visited_urls = set()
        self.raw_html_dir = Path('raw_html')
        self.raw_html_dir.mkdir(exist_ok=True)
        self.use_tor = use_tor
        
        # Load and apply Tor configuration if enabled
        if self.use_tor:
            self._configure_tor()
    
    def _configure_tor(self):
        """Configure Tor proxy settings from tor_config.json"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tor_config.json')
            with open(config_path, 'r') as f:
                tor_config = json.load(f)
            
            # Force enable Tor when use_tor=True
            tor_config['enabled'] = True
            
            # Update custom settings for Tor with SOCKS5 support
            proxy_host = tor_config['proxy']['host']
            proxy_port = tor_config['proxy']['port']
            
            self.custom_settings.update({
                'DOWNLOAD_DELAY': tor_config.get('request_delay', 3),
                'CONCURRENT_REQUESTS': tor_config.get('concurrent_requests', 2),
                'DOWNLOAD_TIMEOUT': tor_config.get('timeout', 120),
                'RETRY_TIMES': tor_config.get('retry_times', 3),
                'ROBOTSTXT_OBEY': False,  # Disable robots.txt for .onion sites
                'HTTPCACHE_ENABLED': False,
                'DOWNLOAD_HANDLERS': {
                    'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
                    'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
                },
            })
            
            # Set SOCKS5 proxy - use socks5 with txsocksx
            self.tor_proxy = f"socks5://{proxy_host}:{proxy_port}"
            
            # Update headers if specified
            if 'headers' in tor_config and 'User-Agent' in tor_config['headers']:
                self.custom_settings['USER_AGENT'] = tor_config['headers']['User-Agent']
            
            self.logger.info(f"[TOR] Tor SOCKS5 proxy configured: {self.tor_proxy}")
        except Exception as e:
            self.logger.error(f"[TOR] Failed to load Tor config: {e}")
            self.tor_proxy = None
    
    def start_requests(self):
        """Generate initial requests with proxy if using Tor"""
        for url in self.start_urls:
            request = scrapy.Request(url, callback=self.parse, errback=self.handle_error)
            if self.use_tor and hasattr(self, 'tor_proxy'):
                request.meta['proxy'] = self.tor_proxy
                self.logger.info(f"[TOR] Request via proxy: {url}")
            yield request
    
    def parse(self, response):
        url = response.url
        
        if url in self.visited_urls:
            return
        
        self.visited_urls.add(url)
        
        self.logger.info(f'Processing: {url}')
        
        html_content = response.text
        url_hash = hashlib.md5(url.encode()).hexdigest()
        html_filename = self.raw_html_dir / f"{url_hash}.html"
        
        with open(html_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        if self.parser and self.analyzer and self.storage:
            clean_text = self.parser.extract_text(html_content)
            
            report = self.analyzer.generate_report(clean_text, url)
            
            self.storage.save_report(report)
            
            self.logger.info(f'Report saved for: {url} | Threat Score: {report.get("threat_score", 0)}')
        
        links = response.css('a::attr(href)').getall()
        
        for link in links:
            absolute_url = response.urljoin(link)
            
            if self._is_valid_url(absolute_url) and absolute_url not in self.visited_urls:
                if response.meta.get('depth', 0) < self.custom_settings['DEPTH_LIMIT']:
                    request = scrapy.Request(
                        absolute_url,
                        callback=self.parse,
                        errback=self.handle_error,
                        dont_filter=False
                    )
                    # Add proxy to request meta if using Tor
                    if self.use_tor and hasattr(self, 'tor_proxy'):
                        request.meta['proxy'] = self.tor_proxy
                    yield request
    
    def _is_valid_url(self, url):
        try:
            parsed = urlparse(url)
            if not (parsed.netloc and parsed.scheme):
                return False
            # Support both surface web and dark web (.onion)
            if self.use_tor:
                if parsed.scheme not in ['http', 'https']:
                    return False
            else:
                if parsed.scheme not in ['http', 'https']:
                    return False
                # Reject .onion URLs when not using Tor
                if parsed.netloc.endswith('.onion'):
                    return False
            if any(ext in url.lower() for ext in ['.pdf', '.jpg', '.png', '.gif', '.zip', '.mp4', '.mp3']):
                return False
            return True
        except:
            return False
    
    def handle_error(self, failure):
        self.logger.error(f'Request failed: {failure.request.url}')


def start_simple_crawler(seed_urls, analyzer=None, parser=None, storage=None, use_tor=False):
    # Build settings dictionary
    settings = {
        'DEPTH_LIMIT': 2,
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_DELAY': 1,
        'ROBOTSTXT_OBEY': True,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'LOG_LEVEL': 'INFO',
    }
    
    # Override settings for Tor if enabled
    if use_tor:
        import json
        import os
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tor_config.json')
        with open(config_path, 'r') as f:
            tor_config = json.load(f)
        
        proxy_host = tor_config['proxy']['host']
        proxy_port = tor_config['proxy']['port']
        
        settings.update({
            'DOWNLOAD_DELAY': tor_config.get('request_delay', 3),
            'CONCURRENT_REQUESTS': tor_config.get('concurrent_requests', 2),
            'DOWNLOAD_TIMEOUT': tor_config.get('timeout', 120),
            'RETRY_TIMES': tor_config.get('retry_times', 3),
            'ROBOTSTXT_OBEY': False,
            'HTTPCACHE_ENABLED': False,
        })
        
        # Use custom SOCKS5 download handler
        settings['DOWNLOAD_HANDLERS'] = {
            'http': 'scripts.socks5_handler.SOCKS5DownloadHandler',
            'https': 'scripts.socks5_handler.SOCKS5DownloadHandler',
        }
    
    process = CrawlerProcess(settings=settings)
    
    process.crawl(
        SimpleIntelligenceCrawler,
        seed_urls=seed_urls,
        analyzer=analyzer,
        parser=parser,
        storage=storage,
        use_tor=use_tor
    )
    
    process.start()
