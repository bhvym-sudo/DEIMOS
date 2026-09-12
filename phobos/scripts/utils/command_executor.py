"""
Command Executor - Backend command system for PHOBOS
All business logic is executed through this command-driven architecture.
"""

import os
import sys
import json
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QProcess


class CommandResult:
    """Result object returned by command execution"""
    def __init__(self, success=True, message="", data=None):
        self.success = success
        self.message = message
        self.data = data or {}
        self.timestamp = datetime.now().strftime("%H:%M:%S")


class CommandExecutor(QObject):
    """
    Central command executor that routes commands to appropriate handlers.
    All UI operations must go through this executor.
    """
    
    # Signals for logging to different tabs
    system_log_signal = pyqtSignal(str)
    tor_log_signal = pyqtSignal(str)
    
    # Signals for UI updates
    ui_update_signal = pyqtSignal(str, object)  # (update_type, data)
    
    def __init__(self):
        super().__init__()
        self.handlers = {}
        self.processes = {}
        self.config = {}
        
        # Initialize command handlers
        self._register_handlers()
        
    def _register_handlers(self):
        """Register all command handlers"""
        # Crawler commands
        self.handlers['crawl'] = CrawlCommandHandler(self)
        
        # Tor commands
        self.handlers['tor'] = TorCommandHandler(self)
        
        # Log commands
        self.handlers['logs'] = LogCommandHandler(self)
        
        # Seed URL commands
        self.handlers['seed'] = SeedCommandHandler(self)
        
        # Intelligence commands
        self.handlers['intel'] = IntelligenceCommandHandler(self)
        
        # Profile commands
        self.handlers['profile'] = ProfileCommandHandler(self)
        
        # Config commands
        self.handlers['config'] = ConfigCommandHandler(self)
        
        # Briefing/Report commands
        self.handlers['report'] = ReportCommandHandler(self)
        
    def run(self, command_string):
        """
        Parse and execute a command string.
        Format: <action> <target> --option=value --flag
        Example: crawl start --depth=2 --delay=1
        """
        # Log the command
        self.system_log_signal.emit(f"[COMMAND] {command_string}")
        
        try:
            # Parse command
            parts = command_string.strip().split()
            if not parts:
                return CommandResult(False, "Empty command")
            
            action = parts[0].lower()
            
            # Check if handler exists
            if action not in self.handlers:
                error_msg = f"Unknown command: {action}"
                self.system_log_signal.emit(f"[ERROR] {error_msg}")
                return CommandResult(False, error_msg)
            
            # Extract target and options
            target = parts[1] if len(parts) > 1 and not parts[1].startswith('--') else None
            options = self._parse_options(parts)
            
            # Execute command
            handler = self.handlers[action]
            result = handler.execute(target, options)
            
            # Log result
            if result.success:
                if result.message:
                    self.system_log_signal.emit(f"[SUCCESS] {result.message}")
            else:
                self.system_log_signal.emit(f"[ERROR] {result.message}")
            
            return result
            
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            self.system_log_signal.emit(f"[ERROR] {error_msg}")
            return CommandResult(False, error_msg)
    
    def _parse_options(self, parts):
        """Parse command line options"""
        options = {}
        flags = []
        
        for part in parts[1:]:
            if part.startswith('--'):
                # Remove leading --
                option = part[2:]
                
                if '=' in option:
                    # Option with value: --key=value
                    key, value = option.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    options[key] = value
                else:
                    # Boolean flag: --flag
                    flags.append(option)
                    options[option] = True
        
        return options
    
    def set_config(self, key, value):
        """Set configuration value"""
        self.config[key] = value
    
    def get_config(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)


class BaseCommandHandler:
    """Base class for command handlers"""
    
    def __init__(self, executor):
        self.executor = executor
        self.project_dir = os.path.dirname(os.path.abspath(__file__))
    
    def execute(self, target, options):
        """Execute command - to be implemented by subclasses"""
        raise NotImplementedError
    
    def log_system(self, message):
        """Log to system logs"""
        self.executor.system_log_signal.emit(message)
    
    def log_tor(self, message):
        """Log to tor logs"""
        self.executor.tor_log_signal.emit(message)
    
    def update_ui(self, update_type, data):
        """Request UI update"""
        self.executor.ui_update_signal.emit(update_type, data)


class CrawlCommandHandler(BaseCommandHandler):
    """Handler for crawl commands"""
    
    def execute(self, target, options):
        if target == 'start':
            return self._start_crawl(options)
        elif target == 'stop':
            return self._stop_crawl(options)
        else:
            return CommandResult(False, f"Unknown crawl target: {target}")
    
    def _start_crawl(self, options):
        """Start crawler with options"""
        # Get configuration
        depth = int(options.get('depth', self.executor.get_config('depth', 2)))
        delay = int(options.get('delay', self.executor.get_config('delay', 1)))
        use_tor = options.get('tor', self.executor.get_config('use_tor', False))
        obey_robots = options.get('robots', self.executor.get_config('obey_robots', True))
        web_mode = options.get('mode', self.executor.get_config('web_mode', 'surface'))
        
        # Load seed URLs
        seed_file = os.path.join(self.project_dir, 'seed_urls.json')
        try:
            with open(seed_file, 'r') as f:
                all_urls = json.load(f)
            
            # Determine which URLs to use
            if web_mode == 'dark' or use_tor:
                seed_urls = all_urls.get('dark_web', [])
                web_type = "Dark Web"
            else:
                seed_urls = all_urls.get('surface_web', [])
                web_type = "Surface Web"
            
            if not seed_urls:
                return CommandResult(False, f"No {web_type} seed URLs found")
            
            urls_list = [url_data['url'] for url_data in seed_urls]
            
        except FileNotFoundError:
            return CommandResult(False, "seed_urls.json not found")
        except Exception as e:
            return CommandResult(False, f"Failed to load seed URLs: {str(e)}")
        
        # Log configuration
        self.log_system(f"[CONFIG] Mode: {web_type}")
        self.log_system(f"[CONFIG] Total Seed URLs: {len(urls_list)}")
        for i, url_data in enumerate(seed_urls, 1):
            self.log_system(f"[URL] {i}. {url_data['url']}")
        self.log_system(f"[CONFIG] Depth Limit: {depth}")
        self.log_system(f"[CONFIG] Download Delay: {delay}s")
        self.log_system(f"[CONFIG] Robots.txt: {'Enabled' if obey_robots else 'Disabled'}")
        if use_tor or web_mode == 'dark':
            self.log_system("[CONFIG] Tor proxy enabled for Dark Web crawling")
        
        # Create crawler process
        crawler_process = QProcess()
        
        # Create config file
        config = {
            'seed_urls': urls_list,
            'depth_limit': depth,
            'download_delay': delay,
            'obey_robots': obey_robots,
            'use_tor': use_tor or (web_mode == 'dark')
        }
        
        config_file = os.path.join(self.project_dir, 'config_files', 'crawler_config.json')
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Setup process handlers
        def handle_output():
            data = crawler_process.readAllStandardOutput()
            output = bytes(data).decode("utf8").strip()
            if output:
                for line in output.split('\n'):
                    if line.strip():
                        self.log_system(line.strip())
        
        def handle_error():
            data = crawler_process.readAllStandardError()
            error = bytes(data).decode("utf8").strip()
            if error:
                for line in error.split('\n'):
                    if line.strip():
                        self.log_system(f"[WARN] {line.strip()}")
        
        def handle_finished():
            self.log_system("[PROCESS] Crawler process finished")
            self.update_ui('crawler_stopped', {})
        
        crawler_process.readyReadStandardOutput.connect(handle_output)
        crawler_process.readyReadStandardError.connect(handle_error)
        crawler_process.finished.connect(handle_finished)
        
        # Start process
        python_exe = sys.executable
        crawler_script = os.path.join(self.project_dir, 'run_crawler.py')
        
        crawler_process.start(python_exe, [crawler_script])
        
        # Store process
        self.executor.processes['crawler'] = crawler_process
        
        # Update UI
        self.update_ui('crawler_started', {'web_type': web_type})
        
        self.log_system(f"[START] Crawler process started in {web_type} mode")
        
        return CommandResult(True, f"Crawler started in {web_type} mode", {'web_type': web_type})
    
    def _stop_crawl(self, options):
        """Stop crawler"""
        if 'crawler' not in self.executor.processes:
            return CommandResult(False, "Crawler is not running")
        
        crawler_process = self.executor.processes['crawler']
        
        if crawler_process.state() != QProcess.Running:
            return CommandResult(False, "Crawler is not running")
        
        self.log_system("[STOP] Stopping crawler...")
        crawler_process.terminate()
        
        if not crawler_process.waitForFinished(3000):
            crawler_process.kill()
            self.log_system("[STOP] Crawler forcefully terminated")
        
        del self.executor.processes['crawler']
        self.update_ui('crawler_stopped', {})
        
        return CommandResult(True, "Crawler stopped")


class TorCommandHandler(BaseCommandHandler):
    """Handler for Tor commands"""
    
    def execute(self, target, options):
        if target == 'start':
            return self._start_tor(options)
        elif target == 'stop':
            return self._stop_tor(options)
        elif target == 'status':
            return self._tor_status(options)
        else:
            return CommandResult(False, f"Unknown tor target: {target}")
    
    def _start_tor(self, options):
        """Start Tor process"""
        if 'tor' in self.executor.processes:
            tor_process = self.executor.processes['tor']
            if tor_process.state() == QProcess.Running:
                return CommandResult(False, "Tor is already running")
        
        # Find tor.exe
        tor_path = os.path.join(self.project_dir, 'tor', 'tor.exe')
        
        if not os.path.exists(tor_path):
            tor_path = os.path.join(self.project_dir, 'tor.exe')
        
        if not os.path.exists(tor_path):
            return CommandResult(False, "tor.exe not found")
        
        # Create Tor process
        tor_process = QProcess()
        
        # Setup handlers
        def handle_output():
            data = tor_process.readAllStandardOutput()
            output = bytes(data).decode("utf8", errors='ignore').strip()
            if output:
                for line in output.split('\n'):
                    if line.strip():
                        self.log_tor(line.strip())
        
        def handle_error():
            data = tor_process.readAllStandardError()
            error = bytes(data).decode("utf8", errors='ignore').strip()
            if error:
                for line in error.split('\n'):
                    if line.strip():
                        self.log_tor(line.strip())
        
        def handle_finished():
            self.log_tor("[TOR] Tor process stopped")
            self.log_system("[TOR] Tor process stopped")
            self.update_ui('tor_stopped', {})
        
        tor_process.readyReadStandardOutput.connect(handle_output)
        tor_process.readyReadStandardError.connect(handle_error)
        tor_process.finished.connect(handle_finished)
        
        # Start Tor
        self.log_system("[TOR] Starting Tor process...")
        self.log_tor("[TOR] Starting Tor process...")
        self.log_tor(f"[TOR] Executable: {tor_path}")
        
        tor_process.start(tor_path, [])
        
        # Store process
        self.executor.processes['tor'] = tor_process
        
        # Update UI
        self.update_ui('tor_started', {})
        self.update_ui('switch_to_tor_logs', {})
        
        return CommandResult(True, "Tor started successfully")
    
    def _stop_tor(self, options):
        """Stop Tor process"""
        if 'tor' not in self.executor.processes:
            return CommandResult(False, "Tor is not running")
        
        tor_process = self.executor.processes['tor']
        
        if tor_process.state() != QProcess.Running:
            return CommandResult(False, "Tor is not running")
        
        self.log_system("[TOR] Stopping Tor process...")
        self.log_tor("[TOR] Stopping Tor process...")
        
        tor_process.terminate()
        
        if not tor_process.waitForFinished(3000):
            tor_process.kill()
            self.log_tor("[TOR] Process forcefully terminated")
        
        del self.executor.processes['tor']
        self.update_ui('tor_stopped', {})
        
        return CommandResult(True, "Tor stopped")
    
    def _tor_status(self, options):
        """Check Tor status"""
        if 'tor' in self.executor.processes:
            tor_process = self.executor.processes['tor']
            if tor_process.state() == QProcess.Running:
                return CommandResult(True, "Tor is running")
        
        return CommandResult(True, "Tor is stopped")


class LogCommandHandler(BaseCommandHandler):
    """Handler for log commands"""
    
    def execute(self, target, options):
        if target == 'clear':
            log_type = options.get('type', 'system')
            return self._clear_logs(log_type)
        else:
            return CommandResult(False, f"Unknown logs target: {target}")
    
    def _clear_logs(self, log_type):
        """Clear logs"""
        if log_type == 'system':
            self.update_ui('clear_system_logs', {})
            self.log_system("[SYSTEM] Logs cleared")
            return CommandResult(True, "System logs cleared")
        elif log_type == 'tor':
            self.update_ui('clear_tor_logs', {})
            return CommandResult(True, "Tor logs cleared")
        elif log_type == 'all':
            self.update_ui('clear_system_logs', {})
            self.update_ui('clear_tor_logs', {})
            self.log_system("[SYSTEM] All logs cleared")
            return CommandResult(True, "All logs cleared")
        else:
            return CommandResult(False, f"Unknown log type: {log_type}")


class SeedCommandHandler(BaseCommandHandler):
    """Handler for seed URL commands"""
    
    def execute(self, target, options):
        if target == 'add':
            return self._add_seed(options)
        elif target == 'delete':
            return self._delete_seed(options)
        elif target == 'list':
            return self._list_seeds(options)
        elif target == 'refresh':
            return self._refresh_seeds(options)
        else:
            return CommandResult(False, f"Unknown seed target: {target}")
    
    def _add_seed(self, options):
        """Add seed URL"""
        url = options.get('url')
        if not url:
            return CommandResult(False, "URL is required (--url=)")
        
        added_by = options.get('by', 'System')
        remarks = options.get('remarks', 'Added via command')
        web_type = options.get('type', 'surface')
        
        # Trigger UI dialog or direct add
        self.update_ui('add_seed_url', {
            'url': url,
            'added_by': added_by,
            'remarks': remarks,
            'web_type': 'dark_web' if web_type == 'dark' else 'surface_web'
        })
        
        return CommandResult(True, f"Seed URL added: {url}")
    
    def _delete_seed(self, options):
        """Delete seed URL"""
        index = options.get('index')
        web_type = options.get('type', 'surface')
        
        if index is None:
            return CommandResult(False, "Index is required (--index=)")
        
        self.update_ui('delete_seed_url', {
            'index': int(index),
            'web_type': 'dark_web' if web_type == 'dark' else 'surface_web'
        })
        
        return CommandResult(True, f"Seed URL deleted at index {index}")
    
    def _list_seeds(self, options):
        """List seed URLs"""
        self.update_ui('refresh_urls_table', {})
        return CommandResult(True, "Seed URLs refreshed")
    
    def _refresh_seeds(self, options):
        """Refresh seed URLs"""
        self.update_ui('refresh_urls_table', {})
        self.update_ui('update_seed_count', {})
        return CommandResult(True, "Seed URLs refreshed")


class IntelligenceCommandHandler(BaseCommandHandler):
    """Handler for intelligence commands"""
    
    def execute(self, target, options):
        if target == 'add-keywords':
            return self._add_keywords(options)
        elif target == 'add-threat':
            return self._add_threat_samples(options)
        elif target == 'add-nonthreat':
            return self._add_nonthreat_samples(options)
        elif target == 'retrain':
            return self._retrain_analyzer(options)
        elif target == 'metrics':
            return self._show_metrics(options)
        elif target == 'refresh':
            return self._refresh_intel(options)
        else:
            return CommandResult(False, f"Unknown intel target: {target}")
    
    def _add_keywords(self, options):
        """Add threat keywords"""
        keywords = options.get('keywords', '')
        if not keywords:
            return CommandResult(False, "Keywords required (--keywords='word1|word2')")
        
        self.update_ui('add_keywords', {'keywords': keywords})
        return CommandResult(True, f"Keywords added: {keywords}")
    
    def _add_threat_samples(self, options):
        """Add threat samples"""
        samples = options.get('samples', '')
        if not samples:
            return CommandResult(False, "Samples required (--samples='sample1|sample2')")
        
        self.update_ui('add_threat_samples', {'samples': samples})
        return CommandResult(True, f"Threat samples added")
    
    def _add_nonthreat_samples(self, options):
        """Add non-threat samples"""
        samples = options.get('samples', '')
        if not samples:
            return CommandResult(False, "Samples required (--samples='sample1|sample2')")
        
        self.update_ui('add_nonthreat_samples', {'samples': samples})
        return CommandResult(True, f"Non-threat samples added")
    
    def _retrain_analyzer(self, options):
        """Retrain analyzer"""
        self.log_system("[INFO] Retraining analyzer...")
        self.update_ui('retrain_analyzer', {})
        return CommandResult(True, "Analyzer retraining initiated")
    
    def _show_metrics(self, options):
        """Show model metrics"""
        self.update_ui('show_model_metrics', {})
        return CommandResult(True, "Model metrics displayed")
    
    def _refresh_intel(self, options):
        """Refresh intelligence display"""
        self.update_ui('refresh_intelligence_display', {})
        return CommandResult(True, "Intelligence data refreshed")


class ProfileCommandHandler(BaseCommandHandler):
    """Handler for profiling commands"""
    
    def execute(self, target, options):
        if target == 'run':
            return self._run_profiling(options)
        elif target == 'search':
            return self._search_profiles(options)
        elif target == 'refresh':
            return self._refresh_profiles(options)
        elif target == 'export':
            return self._export_profile(options)
        else:
            return CommandResult(False, f"Unknown profile target: {target}")
    
    def _run_profiling(self, options):
        """Run person profiling"""
        name = options.get('name', '')
        if not name:
            return CommandResult(False, "Name required (--name='Person Name')")
        
        self.log_system(f"[PROFILER] Running profile for: {name}")
        self.update_ui('run_profiling', {'name': name})
        return CommandResult(True, f"Profiling initiated for: {name}")
    
    def _search_profiles(self, options):
        """Search profiles"""
        query = options.get('query', '')
        self.update_ui('search_profiles', {'query': query})
        return CommandResult(True, f"Searching profiles: {query}")
    
    def _refresh_profiles(self, options):
        """Refresh profiles"""
        self.update_ui('refresh_profiles', {})
        return CommandResult(True, "Profiles refreshed")
    
    def _export_profile(self, options):
        """Export profile"""
        self.update_ui('export_profile', {})
        return CommandResult(True, "Profile export initiated")


class ConfigCommandHandler(BaseCommandHandler):
    """Handler for configuration commands"""
    
    def execute(self, target, options):
        if target == 'set':
            return self._set_config(options)
        elif target == 'get':
            return self._get_config(options)
        elif target == 'show':
            return self._show_config(options)
        else:
            return CommandResult(False, f"Unknown config target: {target}")
    
    def _set_config(self, options):
        """Set configuration"""
        for key, value in options.items():
            self.executor.set_config(key, value)
            self.log_system(f"[CONFIG] {key} = {value}")
        
        # Update UI with config
        self.update_ui('update_config', options)
        
        return CommandResult(True, "Configuration updated", options)
    
    def _get_config(self, options):
        """Get configuration value"""
        key = options.get('key')
        if not key:
            return CommandResult(False, "Key required (--key=)")
        
        value = self.executor.get_config(key)
        self.log_system(f"[CONFIG] {key} = {value}")
        
        return CommandResult(True, f"{key} = {value}", {key: value})
    
    def _show_config(self, options):
        """Show all configuration"""
        for key, value in self.executor.config.items():
            self.log_system(f"[CONFIG] {key} = {value}")
        
        return CommandResult(True, "Configuration displayed", self.executor.config)


class ReportCommandHandler(BaseCommandHandler):
    """Handler for report/briefing commands"""
    
    def execute(self, target, options):
        if target == 'refresh':
            return self._refresh_briefings(options)
        elif target == 'export':
            return self._export_briefing(options)
        else:
            return CommandResult(False, f"Unknown report target: {target}")
    
    def _refresh_briefings(self, options):
        """Refresh briefings"""
        self.update_ui('refresh_briefings', {})
        return CommandResult(True, "Briefings refreshed")
    
    def _export_briefing(self, options):
        """Export briefing"""
        self.update_ui('export_briefing', {})
        return CommandResult(True, "Briefing export initiated")
