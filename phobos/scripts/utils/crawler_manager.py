import json
import subprocess
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

class CrawlerManager:
    def __init__(self, config_path="phobos-crawler/config.json"):
        self.config_path = config_path
        self.crawler_process = None
        
    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except:
            # Return default config if file is corrupted
            return {
                "crawler": {
                    "max_depth": 3,
                    "concurrent_crawlers": 20,
                    "download_delay": 1.0,
                    "use_tor": True,
                    "tor_proxy": "127.0.0.1:9050",
                    "database_path": "../databases/phobos_index.db",
                    "seed_urls_path": "../seed_urls_dark.json"
                },
                "status": {
                    "running": False,
                    "last_started": "",
                    "pages_crawled": 0
                }
            }
    
    def save_config(self, config):
        # Use atomic write to prevent corruption
        temp_fd, temp_path = tempfile.mkstemp(suffix='.json', dir=os.path.dirname(self.config_path))
        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(config, f, indent=4)
            shutil.move(temp_path, self.config_path)
        except:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def update_crawler_settings(self, max_depth, concurrent_crawlers, download_delay):
        config = self.load_config()
        config['crawler']['max_depth'] = max_depth
        config['crawler']['concurrent_crawlers'] = concurrent_crawlers
        config['crawler']['download_delay'] = download_delay
        self.save_config(config)
    
    def start_crawler(self):
        config = self.load_config()
        config['status']['running'] = True
        config['status']['last_started'] = str(datetime.now())
        self.save_config(config)
        
        if self.crawler_process is None:
            os.chdir('phobos-crawler')
            self.crawler_process = subprocess.Popen(['go', 'run', '.'], 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.chdir('..')
        return True
    
    def stop_crawler(self):
        config = self.load_config()
        config['status']['running'] = False
        self.save_config(config)
        
        if self.crawler_process:
            self.crawler_process.terminate()
            self.crawler_process = None
        return True
    
    def get_status(self):
        config = self.load_config()
        return config['status']
    
    def get_crawler_settings(self):
        config = self.load_config()
        return config['crawler']
