"""
SOCKS5 Download Handler for Scrapy using PySocks
Enables crawling through Tor SOCKS5 proxy
"""

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint, HostnameEndpoint
from twisted.web.client import BrowserLikePolicyForHTTPS, Agent, ProxyAgent
from twisted.internet.endpoints import _WrapperEndpoint
import socks
import socket
import os
import json


class SOCKSWrapper:
    """Wrapper to use PySocks with Twisted"""
    
    def __init__(self, proxy_host, proxy_port):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
    
    def connect(self, host, port):
        """Create SOCKS5 connection"""
        sock = socks.socksocket()
        sock.set_proxy(socks.SOCKS5, self.proxy_host, self.proxy_port)
        sock.connect((host, port))
        return sock


class SOCKS5Endpoint:
    """Custom endpoint that creates SOCKS5 connections"""
    
    def __init__(self, reactor, host, port, proxy_host, proxy_port):
        self.reactor = reactor
        self.host = host
        self.port = port
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
    
    def connect(self, protocolFactory):
        """Connect through SOCKS5 proxy"""
        from twisted.internet import defer
        from twisted.internet.protocol import ClientCreator
        
        # Create SOCKS5 socket
        try:
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, self.proxy_host, self.proxy_port)
            sock.connect((self.host, self.port))
            
            # Adopt the socket into Twisted
            from twisted.internet.tcp import Connector
            from twisted.python import log
            
            # Use adoptStreamConnection for the SOCKS socket
            from twisted.internet import tcp
            protocol = protocolFactory.buildProtocol(None)
            transport = tcp.Client(sock, protocol, None, self.reactor)
            protocol.makeConnection(transport)
            
            return defer.succeed(protocol)
        except Exception as e:
            return defer.fail(e)


class SOCKS5DownloadHandler(HTTP11DownloadHandler):
    """Download handler that routes requests through SOCKS5 proxy (Tor)"""
    
    def __init__(self, settings, crawler=None):
        super().__init__(settings, crawler)
        self.settings = settings
        
        # Read proxy settings from tor_config.json
        import json
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tor_config.json')
        try:
            with open(config_path, 'r') as f:
                tor_config = json.load(f)
            self.proxy_host = tor_config['proxy']['host']
            self.proxy_port = tor_config['proxy']['port']
        except Exception:
            # Fallback to default Tor proxy
            self.proxy_host = '127.0.0.1'
            self.proxy_port = 9050
    
    def download_request(self, request, spider):
        """Download page using SOCKS5 proxy via PySocks and requests library"""
        spider.logger.info(f"[TOR] Fetching via SOCKS5: {request.url}")
        
        from twisted.internet import threads
        from scrapy.http import HtmlResponse
        import requests
        
        def _fetch():
            try:
                # Use requests with SOCKS5 proxy
                proxies = {
                    'http': f'socks5h://{self.proxy_host}:{self.proxy_port}',
                    'https': f'socks5h://{self.proxy_host}:{self.proxy_port}'
                }
                
                headers = {
                    'User-Agent': request.headers.get('User-Agent', b'Mozilla/5.0').decode('utf-8')
                }
                
                response = requests.get(
                    request.url,
                    proxies=proxies,
                    headers=headers,
                    timeout=120,
                    allow_redirects=True
                )
                
                spider.logger.info(f"[TOR] Successfully fetched: {request.url} (status: {response.status_code})")
                
                return HtmlResponse(
                    url=request.url,
                    status=response.status_code,
                    body=response.content,
                    encoding='utf-8',
                    request=request
                )
            except Exception as e:
                spider.logger.error(f"[TOR] Failed to fetch {request.url}: {e}")
                raise
        
        # Run in thread to avoid blocking reactor
        return threads.deferToThread(_fetch)
