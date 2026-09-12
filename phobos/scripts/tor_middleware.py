"""
Tor Proxy Middleware for Dark Web Crawling
Handles Tor circuit rotation and proxy configuration
"""

import logging
import json
import os
from scrapy import signals
from scrapy.exceptions import NotConfigured

try:
    from stem import Signal
    from stem.control import Controller
    STEM_AVAILABLE = True
except ImportError:
    STEM_AVAILABLE = False
    logging.warning("stem library not available. Circuit rotation will be disabled.")

logger = logging.getLogger(__name__)


class TorProxyMiddleware:
    """Middleware to route requests through Tor network"""
    
    def __init__(self, tor_config):
        self.tor_config = tor_config
        self.request_count = 0
        self.circuit_rotation_interval = tor_config.get('circuit_rotation_interval', 10)
        self.control_port = tor_config.get('control_port', 9051)
        
    @classmethod
    def from_crawler(cls, crawler):
        # Load Tor configuration
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tor_config.json')
        
        if not os.path.exists(config_path):
            raise NotConfigured("Tor config file not found")
            
        with open(config_path, 'r') as f:
            tor_config = json.load(f)
        
        if not tor_config.get('enabled', False):
            raise NotConfigured("Tor is not enabled in config")
        
        middleware = cls(tor_config)
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware
    
    def spider_opened(self, spider):
        logger.info(f"TorProxyMiddleware enabled for spider: {spider.name}")
        logger.info(f"Tor proxy: {self.tor_config['proxy']['host']}:{self.tor_config['proxy']['port']}")
        logger.info(f"Circuit rotation every {self.circuit_rotation_interval} requests")
    
    def process_request(self, request, spider):
        """Route request through Tor proxy"""
        proxy_url = f"{self.tor_config['proxy']['type']}://{self.tor_config['proxy']['host']}:{self.tor_config['proxy']['port']}"
        request.meta['proxy'] = proxy_url
        
        # Add Tor-friendly headers
        for header, value in self.tor_config.get('headers', {}).items():
            request.headers[header] = value
        
        # Rotate circuit if needed
        self.request_count += 1
        if STEM_AVAILABLE and self.request_count % self.circuit_rotation_interval == 0:
            self._rotate_circuit()
        
        logger.debug(f"Request routed through Tor: {request.url}")
        return None
    
    def _rotate_circuit(self):
        """Rotate Tor circuit to get new IP"""
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
                logger.info("Tor circuit rotated - new IP obtained")
        except Exception as e:
            logger.warning(f"Failed to rotate Tor circuit: {e}")


class TorRetryMiddleware:
    """Retry middleware optimized for Tor network"""
    
    def __init__(self, settings):
        self.max_retry_times = settings.getint('RETRY_TIMES', 3)
        self.retry_http_codes = settings.getlist('RETRY_HTTP_CODES', [500, 502, 503, 504, 408, 429])
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)
    
    def process_response(self, request, response, spider):
        if response.status in self.retry_http_codes:
            retry_count = request.meta.get('retry_times', 0) + 1
            
            if retry_count <= self.max_retry_times:
                logger.warning(f"Retrying {request.url} (attempt {retry_count}/{self.max_retry_times})")
                retry_req = request.copy()
                retry_req.meta['retry_times'] = retry_count
                retry_req.dont_filter = True
                return retry_req
        
        return response
