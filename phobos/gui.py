import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QFrame, QGroupBox, QLineEdit,
    QSpinBox, QCheckBox, QProgressBar, QDialog, QFormLayout, QDialogButtonBox,
    QTextBrowser, QListWidget, QListWidgetItem, QMessageBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QStyle, QStyleOptionButton, QDoubleSpinBox,
    QComboBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QProcess, QRect, QUrl, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor, QPainter, QPen, QKeyEvent
from PyQt5.QtWebEngineWidgets import QWebEngineView
from datetime import datetime
import json
import tempfile
import os
import subprocess
import sqlite3

from scripts.utils.crawler_manager import CrawlerManager


class CustomCheckBox(QCheckBox):
    """Custom checkbox with visible black checkmark on white background"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        
    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Get the indicator rect
            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            indicator_rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, opt, self)
            
            # Draw checkmark
            pen = QPen(QColor(0, 0, 0), 2.5)
            painter.setPen(pen)
            
            # Checkmark coordinates (relative to indicator)
            x = indicator_rect.x()
            y = indicator_rect.y()
            w = indicator_rect.width()
            h = indicator_rect.height()
            
            # Draw checkmark lines
            painter.drawLine(x + int(w*0.25), y + int(h*0.5), x + int(w*0.45), y + int(h*0.7))
            painter.drawLine(x + int(w*0.45), y + int(h*0.7), x + int(w*0.75), y + int(h*0.3))


class AddSeedURLDialog(QDialog):
    def __init__(self, parent=None, web_type="surface_web"):
        super().__init__(parent)
        self.web_type = web_type
        title = "Add Surface Web URL" if web_type == "surface_web" else "Add Dark Web URL (.onion)"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(500)
        
        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #bbbbbb;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
            }
            QLineEdit, QTextEdit {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 8px;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
                selection-background-color: #264f78;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)
        
        layout = QFormLayout()
        self.setLayout(layout)
        
        # URL Entry
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        layout.addRow("Seed URL:", self.url_input)
        
        # Personnel Name Entry
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your name")
        layout.addRow("Added By:", self.name_input)
        
        # Remarks Entry
        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText("Enter reason for adding this URL...")
        self.remarks_input.setMaximumHeight(100)
        layout.addRow("Remarks:", self.remarks_input)
        
        # Dialog Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def validate_and_accept(self):
        if not self.url_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "URL cannot be empty!")
            return
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Name cannot be empty!")
            return
        if not self.remarks_input.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "Remarks cannot be empty!")
            return
        self.accept()
    
    def get_data(self):
        return {
            "url": self.url_input.text().strip(),
            "added_by": self.name_input.text().strip(),
            "remarks": self.remarks_input.toPlainText().strip(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "web_type": self.web_type
        }


class CrawlerProcess(QProcess):
    log_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.readyReadStandardOutput.connect(self.handle_stdout)
        self.readyReadStandardError.connect(self.handle_stderr)
        self.finished.connect(self.process_finished)
    
    def handle_stdout(self):
        data = self.readAllStandardOutput()
        stdout = bytes(data).decode("utf8").strip()
        if stdout:
            for line in stdout.split('\n'):
                if line.strip():
                    self.log_signal.emit(line.strip())
    
    def handle_stderr(self):
        data = self.readAllStandardError()
        stderr = bytes(data).decode("utf8").strip()
        if stderr:
            for line in stderr.split('\n'):
                if line.strip():
                    self.log_signal.emit(f"[WARN] {line.strip()}")
    
    def process_finished(self):
        self.log_signal.emit("[PROCESS] Crawler process finished")


class TorProcess(QProcess):
    log_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.readyReadStandardOutput.connect(self.handle_stdout)
        self.readyReadStandardError.connect(self.handle_stderr)
        self.finished.connect(self.process_finished)
    
    def handle_stdout(self):
        data = self.readAllStandardOutput()
        stdout = bytes(data).decode("utf8", errors='ignore').strip()
        if stdout:
            for line in stdout.split('\n'):
                if line.strip():
                    self.log_signal.emit(line.strip())
    
    def handle_stderr(self):
        data = self.readAllStandardError()
        stderr = bytes(data).decode("utf8", errors='ignore').strip()
        if stderr:
            for line in stderr.split('\n'):
                if line.strip():
                    self.log_signal.emit(line.strip())
    
    def process_finished(self):
        self.log_signal.emit("[TOR] Tor process stopped")


class PHOBOSGui(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Kill any orphaned crawler processes from previous runs
        self.cleanup_orphaned_processes()
        
        self.crawler_manager = CrawlerManager()
        self.go_crawler_process = None
        self.tor_process = None
        self.flask_process = None
        self.go_crawler_logs = []
        
        self.seed_urls_file = os.path.join(os.path.dirname(__file__), 'config_files', 'seed_urls_dark.json')
        self.intelligence_data_file = os.path.join(os.path.dirname(__file__), 'config_files', 'intelligence_data_new.json')
        
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_crawler_status)
        
        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.read_crawler_logs)
        
        self.init_ui()
        
        self.load_crawler_config()
    
    def cleanup_orphaned_processes(self):
        """Kill any leftover phobos-crawler.exe processes from previous runs"""
        try:
            import subprocess
            result = subprocess.run(['taskkill', '/F', '/IM', 'phobos-crawler.exe'], 
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                print("[CLEANUP] Killed orphaned crawler processes")
        except:
            pass
    
    def init_ui(self):
        self.setWindowTitle("PHOBOS - Intelligence Gathering Platform")
        self.setGeometry(100, 100, 1400, 800)
        
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(25, 25, 25))
        palette.setColor(QPalette.WindowText, QColor(187, 187, 187))
        palette.setColor(QPalette.Base, QColor(15, 15, 15))
        palette.setColor(QPalette.AlternateBase, QColor(20, 20, 20))
        palette.setColor(QPalette.Text, QColor(187, 187, 187))
        palette.setColor(QPalette.Button, QColor(30, 30, 30))
        palette.setColor(QPalette.ButtonText, QColor(187, 187, 187))
        self.setPalette(palette)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Top toolbar/header
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-bottom: 1px solid #0a0a0a;
            }
        """)
        header.setFixedHeight(50)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 0, 12, 0)
        header.setLayout(header_layout)
        
        title_label = QLabel("PHOBOS")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #ff6c6c;
                font-family: 'Segoe UI', 'Arial';
                font-size: 22px;
                font-weight: bold;
                border: none;
                background: transparent;
            }
        """)
        header_layout.addWidget(title_label)
        
        main_layout.addWidget(header)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #0a0a0a;
                background-color: #1a1a1a;
                border-top: none;
            }
            QTabBar::tab {
                background-color: #252525;
                color: #999999;
                padding: 10px 24px;
                margin-right: 0px;
                border: 1px solid #0a0a0a;
                border-bottom: none;
                font-size: 12px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
                min-width: 90px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                color: #ffffff;
                border-bottom: 2px solid #ff6c6c;
            }
            QTabBar::tab:hover:!selected {
                background-color: #303030;
                color: #cccccc;
            }
        """)
        main_layout.addWidget(self.tabs)
        
        self.create_home_tab()
        self.create_seed_urls_tab()
        self.create_intelligence_tab()
        self.create_report_briefing_tab()
        self.create_database_leaks_tab()
        self.create_profiling_tab()
        
        self.log_message("[SYSTEM] PHOBOS GUI initialized")
        self.log_message("[READY] Awaiting crawler configuration")
    
    def create_home_tab(self):
        home_widget = QWidget()
        home_layout = QHBoxLayout()
        home_widget.setLayout(home_layout)
        
        # Control panel on left side
        self.create_control_panel(home_layout)
        
        # Create subtabs for logs on right side
        self.home_logs_tabs = QTabWidget()
        self.home_logs_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #0a0a0a;
                background-color: #1a1a1a;
                border-top: none;
            }
            QTabBar::tab {
                background-color: #202020;
                color: #999999;
                padding: 8px 18px;
                margin-right: 0px;
                border: 1px solid #0a0a0a;
                border-bottom: none;
                font-size: 11px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                color: #ffffff;
                border-bottom: 2px solid #4EC9B0;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2a2a2a;
                color: #cccccc;
            }
        """)
        
        # System logs tab
        system_logs_widget = QWidget()
        system_logs_layout = QVBoxLayout()
        system_logs_widget.setLayout(system_logs_layout)
        self.create_log_panel_content(system_logs_layout)
        
        # Crawler logs tab
        crawler_logs_widget = QWidget()
        crawler_logs_layout = QVBoxLayout()
        crawler_logs_widget.setLayout(crawler_logs_layout)
        self.create_crawler_logs_panel(crawler_logs_layout)
        
        # Tor logs tab
        tor_logs_widget = QWidget()
        tor_logs_layout = QVBoxLayout()
        tor_logs_widget.setLayout(tor_logs_layout)
        
        self.tor_log_display = QTextEdit()
        self.tor_log_display.setReadOnly(True)
        self.tor_log_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
                font-weight: normal;
                border: 1px solid #252525;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        
        font = QFont("Consolas", 13)
        self.tor_log_display.setFont(font)
        
        tor_logs_layout.addWidget(self.tor_log_display)
        
        self.home_logs_tabs.addTab(system_logs_widget, "SYSTEM LOGS")
        self.home_logs_tabs.addTab(crawler_logs_widget, "CRAWLER LOGS")
        self.home_logs_tabs.addTab(tor_logs_widget, "TOR LOGS")
        
        home_layout.addWidget(self.home_logs_tabs)
        
        self.tabs.addTab(home_widget, "HOME")
    
    def create_seed_urls_tab(self):
        urls_widget = QWidget()
        urls_layout = QVBoxLayout()
        urls_widget.setLayout(urls_layout)
        
        # Create Dark Web URL table
        darkweb_widget = self.create_url_table_widget("dark_web")
        urls_layout.addWidget(darkweb_widget)
        
        self.tabs.addTab(urls_widget, "SEED URLs")
        
        self.refresh_urls_table()
    
    def create_url_table_widget(self, web_type):
        """Create a URL table widget for surface or dark web"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        header_layout = QHBoxLayout()
        
        # Count label
        count_label = QLabel(f"Total URLs: 0")
        count_label.setObjectName(f"{web_type}_count_label")
        count_label.setStyleSheet("""
            QLabel {
                color: #ff9933;
                font-weight: normal;
                font-size: 13px;
                font-family: 'Segoe UI', 'Arial';
                padding: 4px;
                background: transparent;
            }
        """)
        header_layout.addWidget(count_label)
        
        # Store reference
        if web_type == "surface_web":
            self.surface_count_label = count_label
        else:
            self.darkweb_count_label = count_label
        
        header_layout.addStretch()
        
        # Add URL button
        add_url_btn = QPushButton("ADD NEW URL")
        add_url_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff9933;
            }
            QPushButton:pressed {
                background-color: #ff9933;
                color: #0a0a0a;
            }
        """)
        add_url_btn.clicked.connect(lambda: self.add_seed_url_and_refresh(web_type))
        header_layout.addWidget(add_url_btn)
        
        # Refresh button
        refresh_btn = QPushButton("REFRESH")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_urls_table)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Create table
        table = QTableWidget()
        table.setObjectName(f"{web_type}_table")
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["#", "URL", "Added By", "Timestamp", "Remarks"])
        table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #252525;
                color: #cccccc;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px;
                border: none;
                border-right: 1px solid #1a1a1a;
                border-bottom: 1px solid #1a1a1a;
            }
        """)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0f0f0f;
                color: #d4d4d4;
                gridline-color: #1a1a1a;
                border: 1px solid #252525;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #1a1a1a;
            }
            QTableWidget::item:selected {
                background-color: #264f78;
                color: #ffffff;
            }
            QTableWidget::item:hover {
                background-color: #1a1a1a;
            }
        """)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        
        # Store reference
        if web_type == "surface_web":
            self.surface_urls_table = table
        else:
            self.darkweb_urls_table = table
        
        layout.addWidget(table)
        
        # Delete button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        delete_btn = QPushButton("DELETE SELECTED")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ff6c6c;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff6c6c;
            }
            QPushButton:pressed {
                background-color: #ff6c6c;
                color: #0a0a0a;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_selected_url(web_type))
        button_layout.addWidget(delete_btn)
        
        layout.addLayout(button_layout)
        
        return widget
    
    def create_intelligence_tab(self):
        intel_widget = QWidget()
        intel_layout = QHBoxLayout()
        intel_widget.setLayout(intel_layout)
        
        input_panel = QFrame()
        input_panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-right: 1px solid #0a0a0a;
            }
        """)
        input_panel.setMaximumWidth(400)
        input_panel_layout = QVBoxLayout()
        input_panel.setLayout(input_panel_layout)
        
        keywords_group = QGroupBox("Threat Keywords")
        keywords_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        keywords_layout = QVBoxLayout()
        keywords_group.setLayout(keywords_layout)
        
        keywords_label = QLabel("Enter keywords (separate with |):")
        keywords_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial';")
        keywords_layout.addWidget(keywords_label)
        
        self.keywords_input = QTextEdit()
        self.keywords_input.setMaximumHeight(80)
        self.keywords_input.setPlaceholderText("keyword1 | keyword2 | keyword3")
        self.keywords_input.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 8px;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
                selection-background-color: #264f78;
            }
            QTextEdit:focus {
                border: 1px solid #ff9933;
            }
        """)
        keywords_layout.addWidget(self.keywords_input)
        
        add_keywords_btn = QPushButton("ADD KEYWORDS")
        add_keywords_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ff9933;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 10px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff9933;
            }
            QPushButton:pressed {
                background-color: #ff9933;
                color: #0a0a0a;
            }
        """)
        add_keywords_btn.clicked.connect(self.add_keywords)
        keywords_layout.addWidget(add_keywords_btn)
        
        input_panel_layout.addWidget(keywords_group)
        
        threat_group = QGroupBox("Threatening Samples")
        threat_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        threat_layout = QVBoxLayout()
        threat_group.setLayout(threat_layout)
        
        threat_label = QLabel("Enter samples (separate with |):")
        threat_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial';")
        threat_layout.addWidget(threat_label)
        
        self.threat_input = QTextEdit()
        self.threat_input.setMaximumHeight(80)
        self.threat_input.setPlaceholderText("sample1 | sample2 | sample3")
        self.threat_input.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                color: #ff6c6c;
                border: 1px solid #252525;
                padding: 8px;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
                selection-background-color: #264f78;
            }
            QTextEdit:focus {
                border: 1px solid #ff6c6c;
            }
        """)
        threat_layout.addWidget(self.threat_input)
        
        add_threat_btn = QPushButton("ADD THREAT SAMPLES")
        add_threat_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ff6c6c;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 10px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff6c6c;
            }
            QPushButton:pressed {
                background-color: #ff6c6c;
                color: #0a0a0a;
            }
        """)
        add_threat_btn.clicked.connect(self.add_threat_samples)
        threat_layout.addWidget(add_threat_btn)
        
        input_panel_layout.addWidget(threat_group)
        
        non_threat_group = QGroupBox("Non-Threatening Samples")
        non_threat_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        non_threat_layout = QVBoxLayout()
        non_threat_group.setLayout(non_threat_layout)
        
        non_threat_label = QLabel("Enter samples (separate with |):")
        non_threat_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial';")
        non_threat_layout.addWidget(non_threat_label)
        
        self.non_threat_input = QTextEdit()
        self.non_threat_input.setMaximumHeight(80)
        self.non_threat_input.setPlaceholderText("sample1 | sample2 | sample3")
        self.non_threat_input.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                color: #4EC9B0;
                border: 1px solid #252525;
                padding: 8px;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
                selection-background-color: #264f78;
            }
            QTextEdit:focus {
                border: 1px solid #4EC9B0;
            }
        """)
        non_threat_layout.addWidget(self.non_threat_input)
        
        add_non_threat_btn = QPushButton("ADD NON-THREAT SAMPLES")
        add_non_threat_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #4EC9B0;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 10px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4EC9B0;
            }
            QPushButton:pressed {
                background-color: #4EC9B0;
                color: #0a0a0a;
            }
        """)
        add_non_threat_btn.clicked.connect(self.add_non_threat_samples)
        non_threat_layout.addWidget(add_non_threat_btn)
        
        input_panel_layout.addWidget(non_threat_group)
        
        retrain_btn = QPushButton("RETRAIN ANALYZER")
        retrain_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #007acc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
            QPushButton:pressed {
                background-color: #007acc;
                color: #0a0a0a;
            }
        """)
        retrain_btn.clicked.connect(self.retrain_analyzer)
        input_panel_layout.addWidget(retrain_btn)
        
        model_info_btn = QPushButton("VIEW MODEL METRICS")
        model_info_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #dcdcaa;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
                margin-top: 5px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #dcdcaa;
            }
            QPushButton:pressed {
                background-color: #dcdcaa;
                color: #0a0a0a;
            }
        """)
        model_info_btn.clicked.connect(self.show_model_metrics)
        input_panel_layout.addWidget(model_info_btn)
        
        input_panel_layout.addStretch()
        
        intel_layout.addWidget(input_panel)
        
        display_panel = QFrame()
        display_panel.setStyleSheet("""
            QFrame {
                background-color: #0f0f0f;
                border: 1px solid #252525;
            }
        """)
        display_layout = QVBoxLayout()
        display_panel.setLayout(display_layout)
        
        header_layout = QHBoxLayout()
        
        intel_header = QLabel("Intelligence Data")
        intel_header.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px;
                background-color: #1a1a1a;
                border-bottom: 1px solid #252525;
            }
        """)
        header_layout.addWidget(intel_header)
        
        header_layout.addStretch()
        
        refresh_intel_btn = QPushButton("REFRESH")
        refresh_intel_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        refresh_intel_btn.clicked.connect(self.refresh_intelligence_display)
        header_layout.addWidget(refresh_intel_btn)
        
        display_layout.addLayout(header_layout)
        
        self.intel_display = QTextEdit()
        self.intel_display.setReadOnly(True)
        self.intel_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New';
                font-size: 14px;
                border: none;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        display_layout.addWidget(self.intel_display)
        
        intel_layout.addWidget(display_panel)
        
        self.tabs.addTab(intel_widget, "INTELLIGENCE DATA")
        
        self.refresh_intelligence_display()
    
    def create_report_briefing_tab(self):
        report_widget = QWidget()
        report_layout = QVBoxLayout()
        report_widget.setLayout(report_layout)
        
        # Create sub-tabs for Web View and Portal Reports
        self.report_tabs = QTabWidget()
        self.report_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #0a0a0a;
                background-color: #0a0a0a;
                border-top: none;
            }
            QTabBar::tab {
                background-color: #202020;
                color: #999999;
                padding: 8px 18px;
                margin-right: 0px;
                border: 1px solid #0a0a0a;
                border-bottom: none;
                font-size: 11px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
            }
            QTabBar::tab:selected {
                background-color: #0a0a0a;
                color: #ffffff;
                border-bottom: 2px solid #ff9933;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2a2a2a;
                color: #cccccc;
            }
        """)
        
        # Web View Tab (Flask app)
        web_view_widget = QWidget()
        web_view_layout = QVBoxLayout()
        web_view_widget.setLayout(web_view_layout)
        
        self.report_browser = QWebEngineView()
        self.report_browser.setUrl(QUrl("http://127.0.0.1:7788"))
        self.report_browser.setStyleSheet("background-color: #0a0a0a;")
        web_view_layout.addWidget(self.report_browser)
        
        # Portal Reports Tab (existing reports display)
        portal_reports_widget = QWidget()
        portal_reports_layout = QHBoxLayout()
        portal_reports_widget.setLayout(portal_reports_layout)
        
        sidebar = QFrame()
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-right: 1px solid #0a0a0a;
            }
        """)
        sidebar.setMaximumWidth(350)
        sidebar_layout = QVBoxLayout()
        sidebar.setLayout(sidebar_layout)
        
        sidebar_header = QLabel("Intelligence Briefings")
        sidebar_header.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px;
                background-color: #1a1a1a;
                border-bottom: 1px solid #252525;
            }
        """)
        sidebar_layout.addWidget(sidebar_header)
        
        refresh_briefings_btn = QPushButton("REFRESH BRIEFINGS")
        refresh_briefings_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 10px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        refresh_briefings_btn.clicked.connect(self.refresh_briefings)
        sidebar_layout.addWidget(refresh_briefings_btn)
        
        self.briefings_list = QListWidget()
        self.briefings_list.setStyleSheet("""
            QListWidget {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                font-family: 'Consolas', 'Courier New';
                font-size: 11px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #1a1a1a;
            }
            QListWidget::item:selected {
                background-color: #264f78;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #1a1a1a;
            }
        """)
        self.briefings_list.itemClicked.connect(self.display_briefing_details)
        sidebar_layout.addWidget(self.briefings_list)
        
        portal_reports_layout.addWidget(sidebar)
        
        detail_panel = QFrame()
        detail_panel.setStyleSheet("""
            QFrame {
                background-color: #0f0f0f;
                border: 1px solid #252525;
            }
        """)
        detail_layout = QVBoxLayout()
        detail_panel.setLayout(detail_layout)
        
        detail_header_layout = QHBoxLayout()
        
        self.briefing_title = QLabel("Select a briefing to view details")
        self.briefing_title.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px;
                background-color: #1a1a1a;
                border-bottom: 1px solid #252525;
            }
        """)
        detail_header_layout.addWidget(self.briefing_title)
        
        detail_header_layout.addStretch()
        
        export_btn = QPushButton("EXPORT BRIEFING")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        export_btn.clicked.connect(self.export_current_briefing)
        detail_header_layout.addWidget(export_btn)
        
        detail_layout.addLayout(detail_header_layout)
        
        self.briefing_display = QTextEdit()
        self.briefing_display.setReadOnly(True)
        self.briefing_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #ffffff;
                font-family: 'Consolas', 'Courier New';
                font-size: 15px;
                font-weight: normal;
                border: none;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        detail_layout.addWidget(self.briefing_display)
        
        portal_reports_layout.addWidget(detail_panel)
        
        # Crawled URLs Tab
        crawled_urls_widget = QWidget()
        crawled_urls_layout = QVBoxLayout()
        crawled_urls_widget.setLayout(crawled_urls_layout)
        
        # Header with stats and refresh
        crawled_header = QHBoxLayout()
        
        self.crawled_stats_label = QLabel("Total Crawled: 0 | Active: 0")
        self.crawled_stats_label.setStyleSheet("""
            QLabel {
                color: #4EC9B0;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Consolas', 'Courier New';
                padding: 8px;
            }
        """)
        crawled_header.addWidget(self.crawled_stats_label)
        
        crawled_header.addStretch()
        
        refresh_crawled_btn = QPushButton("REFRESH")
        refresh_crawled_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        refresh_crawled_btn.clicked.connect(self.refresh_crawled_urls)
        crawled_header.addWidget(refresh_crawled_btn)
        
        crawled_urls_layout.addLayout(crawled_header)
        
        # Table for crawled URLs
        self.crawled_urls_table = QTableWidget()
        self.crawled_urls_table.setColumnCount(6)
        self.crawled_urls_table.setHorizontalHeaderLabels(["ID", "URL", "Title", "Domain", "Status", "Crawled At"])
        self.crawled_urls_table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #252525;
                color: #cccccc;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px;
                border: none;
                border-right: 1px solid #1a1a1a;
                border-bottom: 1px solid #1a1a1a;
            }
        """)
        self.crawled_urls_table.setStyleSheet("""
            QTableWidget {
                background-color: #0f0f0f;
                color: #d4d4d4;
                gridline-color: #1a1a1a;
                border: 1px solid #252525;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #1a1a1a;
            }
            QTableWidget::item:selected {
                background-color: #264f78;
                color: #ffffff;
            }
            QTableWidget::item:hover {
                background-color: #1a1a1a;
            }
        """)
        self.crawled_urls_table.horizontalHeader().setStretchLastSection(True)
        self.crawled_urls_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.crawled_urls_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.crawled_urls_table.setSelectionMode(QTableWidget.SingleSelection)
        self.crawled_urls_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        crawled_urls_layout.addWidget(self.crawled_urls_table)
        
        # Search Engine Tab
        search_engine_widget = QWidget()
        search_engine_layout = QVBoxLayout()
        search_engine_widget.setLayout(search_engine_layout)
        
        self.search_browser = QWebEngineView()
        self.search_browser.setUrl(QUrl("http://127.0.0.1:8080"))
        self.search_browser.setStyleSheet("background-color: #0a0a0a;")
        search_engine_layout.addWidget(self.search_browser)
        
        # Add tabs
        self.report_tabs.addTab(search_engine_widget, "SEARCH ENGINE")
        self.report_tabs.addTab(web_view_widget, "THREAT REPORTS")
        self.report_tabs.addTab(crawled_urls_widget, "CRAWLED URLs")
        self.report_tabs.addTab(portal_reports_widget, "PORTAL REPORTS")
        
        report_layout.addWidget(self.report_tabs)
        
        self.tabs.addTab(report_widget, "REPORT BRIEFING")
        
        # Start Flask server in background
        self.start_flask_server()
        
        self.refresh_briefings()
        self.refresh_crawled_urls()
    
    def create_control_panel(self, parent_layout):
        control_frame = QFrame()
        control_frame.setFrameShape(QFrame.StyledPanel)
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-right: 1px solid #0a0a0a;
            }
        """)
        control_frame.setMaximumWidth(400)
        
        control_layout = QVBoxLayout()
        control_frame.setLayout(control_layout)
        
        config_group = QGroupBox("Configuration")
        config_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        config_layout = QVBoxLayout()
        config_group.setLayout(config_layout)
        
        self.seed_count_label = QLabel("Seed URLs: 0")
        self.seed_count_label.setStyleSheet("""
            QLabel {
                color: #ff9933;
                font-size: 13px;
                font-weight: normal;
                font-family: 'Consolas', 'Courier New';
                margin-top: 5px;
                padding: 8px;
                background-color: #0f0f0f;
                border: 1px solid #252525;
            }
        """)
        config_layout.addWidget(self.seed_count_label)
        
        depth_label = QLabel("Max Depth:")
        depth_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial'; margin-top: 10px;")
        config_layout.addWidget(depth_label)
        
        self.depth_spin = QSpinBox()
        self.depth_spin.setMinimum(1)
        self.depth_spin.setMaximum(10)
        self.depth_spin.setValue(3)
        self.depth_spin.setStyleSheet("""
            QSpinBox {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 6px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New';
            }
            QSpinBox:focus {
                border: 1px solid #007acc;
            }
        """)
        config_layout.addWidget(self.depth_spin)
        
        concurrent_label = QLabel("Concurrent Crawlers:")
        concurrent_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial'; margin-top: 10px;")
        config_layout.addWidget(concurrent_label)
        
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setMinimum(1)
        self.concurrent_spin.setMaximum(50)
        self.concurrent_spin.setValue(20)
        self.concurrent_spin.setStyleSheet("""
            QSpinBox {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 6px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New';
            }
            QSpinBox:focus {
                border: 1px solid #007acc;
            }
        """)
        config_layout.addWidget(self.concurrent_spin)
        
        delay_label = QLabel("Download Delay (seconds):")
        delay_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial'; margin-top: 10px;")
        config_layout.addWidget(delay_label)
        
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setMinimum(0.0)
        self.delay_spin.setMaximum(10.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setValue(1.0)
        self.delay_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 6px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New';
            }
            QDoubleSpinBox:focus {
                border: 1px solid #007acc;
            }
        """)
        config_layout.addWidget(self.delay_spin)
        
        tor_proxy_label = QLabel("Tor Proxy:")
        tor_proxy_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-family: 'Segoe UI', 'Arial'; margin-top: 10px;")
        config_layout.addWidget(tor_proxy_label)
        
        self.tor_proxy_input = QLineEdit("127.0.0.1:9050")
        self.tor_proxy_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 6px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New';
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        config_layout.addWidget(self.tor_proxy_input)
        
        mode_label = QLabel("Mode: Dark Web Only (Tor)")
        mode_label.setStyleSheet("""
            QLabel {
                color: #ff9933;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Segoe UI', 'Arial';
                margin-top: 10px;
                padding: 8px;
                background-color: #0f0f0f;
                border: 1px solid #ff9933;
            }
        """)
        config_layout.addWidget(mode_label)
        
        self.pages_crawled_label = QLabel("Pages Crawled: 0")
        self.pages_crawled_label.setStyleSheet("""
            QLabel {
                color: #4EC9B0;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Consolas', 'Courier New';
                margin-top: 5px;
                padding: 8px;
                background-color: #0f0f0f;
                border: 1px solid #252525;
            }
        """)
        config_layout.addWidget(self.pages_crawled_label)
        
        control_layout.addWidget(config_group)
        
        # Update seed count after all widgets are created
        self.update_seed_count()
        
        controls_group = QGroupBox("Crawler Control")
        controls_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        controls_layout = QVBoxLayout()
        controls_group.setLayout(controls_layout)
        
        self.start_button = QPushButton("START CRAWLER")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #4EC9B0;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4EC9B0;
            }
            QPushButton:pressed {
                background-color: #4EC9B0;
                color: #0a0a0a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border-color: #252525;
            }
        """)
        self.start_button.clicked.connect(self.start_crawler)
        controls_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("STOP CRAWLER")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ff6c6c;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff6c6c;
            }
            QPushButton:pressed {
                background-color: #ff6c6c;
                color: #0a0a0a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border-color: #252525;
            }
        """)
        self.stop_button.clicked.connect(self.stop_crawler)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)
        
        self.clear_button = QPushButton("CLEAR LOGS")
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #bbbbbb;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 10px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #bbbbbb;
            }
        """)
        self.clear_button.clicked.connect(self.clear_logs)
        controls_layout.addWidget(self.clear_button)
        
        control_layout.addWidget(controls_group)
        
        # Tor Control Group
        tor_group = QGroupBox("Tor Control")
        tor_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        tor_layout = QVBoxLayout()
        tor_group.setLayout(tor_layout)
        
        self.tor_status_label = QLabel("Tor Status: STOPPED")
        self.tor_status_label.setStyleSheet("""
            QLabel {
                color: #ff6c6c;
                font-size: 13px;
                font-weight: normal;
                padding: 6px;
                font-family: 'Consolas', 'Courier New';
            }
        """)
        tor_layout.addWidget(self.tor_status_label)
        
        self.start_tor_button = QPushButton("START TOR")
        self.start_tor_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #4EC9B0;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4EC9B0;
            }
            QPushButton:pressed {
                background-color: #4EC9B0;
                color: #0a0a0a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border-color: #252525;
            }
        """)
        self.start_tor_button.clicked.connect(self.start_tor)
        tor_layout.addWidget(self.start_tor_button)
        
        self.stop_tor_button = QPushButton("STOP TOR")
        self.stop_tor_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ff6c6c;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                padding: 12px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #ff6c6c;
            }
            QPushButton:pressed {
                background-color: #ff6c6c;
                color: #0a0a0a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border-color: #252525;
            }
        """)
        self.stop_tor_button.clicked.connect(self.stop_tor)
        self.stop_tor_button.setEnabled(False)
        tor_layout.addWidget(self.stop_tor_button)
        
        control_layout.addWidget(tor_group)
        
        status_group = QGroupBox("Status")
        status_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                font-weight: normal;
                font-size: 12px;
                font-family: 'Segoe UI', 'Arial';
                border: 1px solid #252525;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        status_layout = QVBoxLayout()
        status_group.setLayout(status_layout)
        
        self.status_label = QLabel("Status: IDLE")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #4EC9B0;
                font-size: 13px;
                font-weight: normal;
                padding: 6px;
                font-family: 'Consolas', 'Courier New';
            }
        """)
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #252525;
                background-color: #0f0f0f;
                text-align: center;
                color: #d4d4d4;
                font-size: 10px;
                font-family: 'Consolas', 'Courier New';
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #4EC9B0;
            }
        """)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)
        
        control_layout.addWidget(status_group)
        
        control_layout.addStretch()
        
        parent_layout.addWidget(control_frame)
    
    def create_log_panel_content(self, parent_layout):
        """Create the system log display content"""
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
                font-weight: normal;
                border: 1px solid #252525;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        
        font = QFont("Consolas", 13)
        self.log_display.setFont(font)
        
        parent_layout.addWidget(self.log_display)
        
        # Add command console input at bottom
        console_frame = QFrame()
        console_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-top: 1px solid #252525;
            }
        """)
        console_layout = QHBoxLayout()
        console_frame.setLayout(console_layout)
        
        console_label = QLabel("$")
        console_label.setStyleSheet("""
            QLabel {
                color: #4EC9B0;
                font-family: 'Consolas', 'Courier New';
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        console_layout.addWidget(console_label)
        
        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText("Enter command...")
        self.console_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f0f0f;
                color: #d4d4d4;
                border: 1px solid #252525;
                padding: 8px;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
                selection-background-color: #264f78;
            }
            QLineEdit:focus {
                border: 1px solid #4EC9B0;
            }
        """)
        self.console_input.returnPressed.connect(self.execute_console_command)
        console_layout.addWidget(self.console_input)
        
        exec_button = QPushButton("EXECUTE")
        exec_button.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #4EC9B0;
                font-weight: normal;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 16px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4EC9B0;
            }
            QPushButton:pressed {
                background-color: #4EC9B0;
                color: #0a0a0a;
            }
        """)
        exec_button.clicked.connect(self.execute_console_command)
        console_layout.addWidget(exec_button)
        
        parent_layout.addWidget(console_frame)
    
    def create_crawler_logs_panel(self, parent_layout):
        """Create crawler logs display showing Go crawler activity"""
        # Header with stats
        header_layout = QHBoxLayout()
        
        self.crawler_stats_label = QLabel("Crawler: Idle | URLs Processed: 0 | Queue: 0")
        self.crawler_stats_label.setStyleSheet("""
            QLabel {
                color: #4EC9B0;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Consolas', 'Courier New';
                padding: 8px;
            }
        """)
        header_layout.addWidget(self.crawler_stats_label)
        
        header_layout.addStretch()
        
        refresh_crawler_btn = QPushButton("REFRESH")
        refresh_crawler_btn.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #ffffff;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial';
                padding: 8px 14px;
                border: 1px solid #1a1a1a;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #007acc;
            }
        """)
        refresh_crawler_btn.clicked.connect(self.refresh_crawler_logs)
        header_layout.addWidget(refresh_crawler_btn)
        
        parent_layout.addLayout(header_layout)
        
        # Crawler logs display
        self.crawler_log_display = QTextEdit()
        self.crawler_log_display.setReadOnly(True)
        self.crawler_log_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
                font-weight: normal;
                border: 1px solid #252525;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        
        font = QFont("Consolas", 13)
        self.crawler_log_display.setFont(font)
        
        parent_layout.addWidget(self.crawler_log_display)
        
        # Start timer to refresh crawler logs
        self.crawler_log_timer = QTimer()
        self.crawler_log_timer.timeout.connect(self.refresh_crawler_logs)
        self.crawler_log_timer.start(1000)  # Refresh every 1 second for real-time logs
    
    def refresh_crawler_logs(self):
        try:
            # Get stats from database
            db_path = os.path.join(os.path.dirname(__file__), 'databases', 'phobos_index.db')
            
            indexed = 0
            queue = 0
            
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1")
                indexed = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'")
                queue = cursor.fetchone()[0]
                conn.close()
            
            # Check if crawler is running
            status = self.crawler_manager.get_status() if hasattr(self, 'crawler_manager') else {'running': False}
            crawler_status = "RUNNING" if status.get('running') else "IDLE"
            
            self.crawler_stats_label.setText(f"Crawler: {crawler_status} | URLs Processed: {indexed} | Queue: {queue}")
            
            # Display Go crawler logs
            logs = []
            logs.append("╔" + "═"*78 + "╗")
            logs.append("║" + " "*20 + "PHOBOS CRAWLER LIVE LOGS" + " "*35 + "║")
            logs.append("╚" + "═"*78 + "╝")
            logs.append(f"Status: {crawler_status} | Pages: {indexed} | Queue: {queue}")
            logs.append("─"*80)
            logs.append("")
            
            if len(self.go_crawler_logs) > 0:
                # Show last 100 log entries
                for log_line in self.go_crawler_logs[-100:]:
                    logs.append(log_line)
            else:
                logs.append("[INFO] Waiting for crawler to start...")
                logs.append("[INFO] Click 'START CRAWLER' to begin crawling")
            
            self.crawler_log_display.setPlainText("\n".join(logs))
            
            # Auto-scroll to bottom
            scrollbar = self.crawler_log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception as e:
            self.crawler_log_display.setPlainText(f"[ERROR] Failed to update logs: {str(e)}")
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Highlight log keywords with colors
        keywords = ['[WARN]', '[STOP]', '[ERROR]', '[SUCCESS]', '[INFO]', '[START]', '[CONFIG]', '[SYSTEM]', '[READY]', '[ADD]', '[DELETE]', '[SAVE]', '[EXPORT]', '[VIEW]', '[PROFILER]', '[PROCESS]', '[URL']
        
        formatted_message = f"<span style='color: #888888;'>[{timestamp}]</span> {message}"
        
        # Highlight [COMMAND] with orange color first (before other keywords)
        if '[COMMAND]' in formatted_message:
            formatted_message = formatted_message.replace('[COMMAND]', "<span style='color: #ff9933; font-weight: bold;'>[COMMAND]</span>")
        
        # Replace other keywords with cyan-colored versions
        for keyword in keywords:
            if keyword in formatted_message:
                formatted_message = formatted_message.replace(keyword, f"<span style='color: #00ffff; font-weight: bold;'>{keyword}</span>")
        
        self.log_display.append(formatted_message)
        self.log_display.moveCursor(QTextCursor.End)
    
    def load_seed_urls(self, web_type=None):
        """Load seed URLs from JSON file"""
        try:
            if os.path.exists(self.seed_urls_file):
                with open(self.seed_urls_file, 'r') as f:
                    data = json.load(f)
                    if web_type:
                        return data.get(web_type, [])
                    # Return both for compatibility
                    return {
                        'surface_web': data.get('surface_web', []),
                        'dark_web': data.get('dark_web', [])
                    }
            if web_type:
                return []
            return {'surface_web': [], 'dark_web': []}
        except Exception as e:
            self.log_message(f"[ERROR] Failed to load seed URLs: {str(e)}")
            if web_type:
                return []
            return {'surface_web': [], 'dark_web': []}
    
    def save_seed_urls(self, surface_urls=None, dark_urls=None):
        """Save seed URLs to JSON file"""
        try:
            # Load current data
            current_data = self.load_seed_urls()
            
            # Update with new data if provided
            if surface_urls is not None:
                current_data['surface_web'] = surface_urls
            if dark_urls is not None:
                current_data['dark_web'] = dark_urls
            
            with open(self.seed_urls_file, 'w') as f:
                json.dump(current_data, f, indent=2)
            self.log_message("[SAVE] Seed URLs saved successfully")
            return True
        except Exception as e:
            self.log_message(f"[ERROR] Failed to save seed URLs: {str(e)}")
            return False
    
    def update_seed_count(self):
        all_urls = self.load_seed_urls()
        dark_count = len(all_urls.get('dark_web', []))
        
        self.seed_count_label.setText(f"Seed URLs: {dark_count} (Dark Web Only)")
        
        if hasattr(self, 'darkweb_count_label'):
            self.darkweb_count_label.setText(f"Total URLs: {dark_count}")
    
    def refresh_urls_table(self):
        self.log_message("[COMMAND] seed refresh")
        self.log_message("[INFO] Refreshing seed URLs table")
        
        all_urls = self.load_seed_urls()
        
        # Refresh surface web table
        surface_urls = all_urls['surface_web']
        if hasattr(self, 'surface_urls_table'):
            self.surface_urls_table.setRowCount(len(surface_urls))
            for i, url_data in enumerate(surface_urls):
                self.surface_urls_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.surface_urls_table.setItem(i, 1, QTableWidgetItem(url_data['url']))
                self.surface_urls_table.setItem(i, 2, QTableWidgetItem(url_data['added_by']))
                self.surface_urls_table.setItem(i, 3, QTableWidgetItem(url_data['timestamp']))
                self.surface_urls_table.setItem(i, 4, QTableWidgetItem(url_data['remarks']))
        
        # Refresh dark web table
        dark_urls = all_urls['dark_web']
        if hasattr(self, 'darkweb_urls_table'):
            self.darkweb_urls_table.setRowCount(len(dark_urls))
            for i, url_data in enumerate(dark_urls):
                self.darkweb_urls_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.darkweb_urls_table.setItem(i, 1, QTableWidgetItem(url_data['url']))
                self.darkweb_urls_table.setItem(i, 2, QTableWidgetItem(url_data['added_by']))
                self.darkweb_urls_table.setItem(i, 3, QTableWidgetItem(url_data['timestamp']))
                self.darkweb_urls_table.setItem(i, 4, QTableWidgetItem(url_data['remarks']))
        
        self.update_seed_count()
    
    def add_seed_url_and_refresh(self, web_type="surface_web"):
        # Log command
        web_type_display = "dark" if web_type == "dark_web" else "surface"
        self.log_message(f"[COMMAND] seed add --type={web_type_display}")
        self.log_message(f"[INFO] Opening dialog to add {web_type_display} web URL")
        
        dialog = AddSeedURLDialog(self, web_type)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            # Log the full command with parameters
            self.log_message(f"[COMMAND] seed add --url=\"{data['url']}\" --by=\"{data['added_by']}\" --remarks=\"{data['remarks'][:30]}...\" --type={web_type_display}")
            
            all_urls = self.load_seed_urls()
            
            # Add to appropriate list
            all_urls[web_type].append(data)
            
            # Save
            if web_type == "surface_web":
                if self.save_seed_urls(surface_urls=all_urls['surface_web']):
                    self.refresh_urls_table()
                    self.log_message(f"[SUCCESS] Surface web URL added: {data['url']}")
            else:
                if self.save_seed_urls(dark_urls=all_urls['dark_web']):
                    self.refresh_urls_table()
                    self.log_message(f"[SUCCESS] Dark web URL added: {data['url']}")
            
            self.log_message(f"[INFO] Added by: {data['added_by']}")
            self.refresh_urls_table()
            QMessageBox.information(self, "Success", "Seed URL added successfully!")
        else:
            self.log_message(f"[INFO] Seed URL dialog cancelled")
    
    def delete_selected_url(self, web_type="surface_web"):
        # Get the appropriate table
        table = self.surface_urls_table if web_type == "surface_web" else self.darkweb_urls_table
        current_row = table.currentRow()
        
        web_type_display = "dark" if web_type == "dark_web" else "surface"
        
        if current_row < 0:
            self.log_message(f"[ERROR] No URL selected for deletion")
            QMessageBox.warning(self, "Warning", "Please select a URL to delete!")
            return
        
        # Get URL for logging
        all_urls = self.load_seed_urls()
        url_to_delete = all_urls[web_type][current_row]['url']
        
        self.log_message(f"[COMMAND] seed delete --index={current_row} --type={web_type_display}")
        self.log_message(f"[INFO] Requesting deletion of URL: {url_to_delete}")
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                     "Are you sure you want to delete this seed URL?",
                                     QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            deleted_url = all_urls[web_type][current_row]['url']
            all_urls[web_type].pop(current_row)
            
            # Save the updated list
            if web_type == "surface_web":
                success = self.save_seed_urls(surface_urls=all_urls['surface_web'])
            else:
                success = self.save_seed_urls(dark_urls=all_urls['dark_web'])
            
            if success:
                self.log_message(f"[SUCCESS] {web_type.replace('_', ' ').title()} URL deleted: {deleted_url}")
                self.refresh_urls_table()
                QMessageBox.information(self, "Success", "Seed URL deleted successfully!")
        else:
            self.log_message(f"[INFO] Deletion cancelled")
    
    def add_seed_url(self):
        """Open dialog to add a new seed URL"""
        dialog = AddSeedURLDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            seed_urls = self.load_seed_urls()
            seed_urls.append(data)
            
            if self.save_seed_urls(seed_urls):
                self.log_message(f"[ADD] Seed URL added: {data['url']}")
                self.log_message(f"[INFO] Added by: {data['added_by']}")
                self.log_message(f"[INFO] Remarks: {data['remarks']}")
                self.update_seed_count()
                QMessageBox.information(self, "Success", "Seed URL added successfully!")
    
    def start_crawler(self):
        try:
            all_urls = self.load_seed_urls()
            seed_urls = all_urls.get('dark_web', [])
            
            if not seed_urls:
                QMessageBox.warning(self, "No Seed URLs", 
                                  "No Dark Web seed URLs found! Please add .onion URLs before starting the crawler.")
                self.log_message("[ERROR] No Dark Web seed URLs available")
                return
            
            self.log_message("[PHOBOS-CRAWLER] Initializing Go crawler...")
            self.log_message(f"[CONFIG] Mode: Dark Web Only")
            self.log_message(f"[CONFIG] Total Seed URLs: {len(seed_urls)}")
            for i, url_data in enumerate(seed_urls, 1):
                self.log_message(f"[URL {i}] {url_data['url']}")
            self.log_message(f"[CONFIG] Max Depth: {self.depth_spin.value()}")
            self.log_message(f"[CONFIG] Concurrent Crawlers: {self.concurrent_spin.value()}")
            self.log_message(f"[CONFIG] Download Delay: {self.delay_spin.value()}s")
            self.log_message(f"[CONFIG] Tor Proxy: {self.tor_proxy_input.text()}")
            
            self.crawler_manager.update_crawler_settings(
                self.depth_spin.value(),
                self.concurrent_spin.value(),
                self.delay_spin.value()
            )
            
            self.go_crawler_process = QProcess(self)
            self.go_crawler_process.readyReadStandardOutput.connect(self.read_crawler_stdout)
            self.go_crawler_process.readyReadStandardError.connect(self.read_crawler_stderr)
            self.go_crawler_process.finished.connect(self.crawler_finished)
            
            crawler_dir = os.path.join(os.path.dirname(__file__), 'phobos-crawler')
            exe_path = os.path.join(crawler_dir, 'phobos-crawler.exe')
            
            if not os.path.exists(exe_path):
                QMessageBox.critical(self, "Error", "phobos-crawler.exe not found! Please build it first.")
                return
            
            self.go_crawler_process.setWorkingDirectory(crawler_dir)
            self.go_crawler_process.start(exe_path)
            
            self.crawler_manager.start_crawler()
            
            self.log_message("[SYSTEM] Go crawler process started")
            
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText("Status: RUNNING (Dark Web)")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #FFFF00;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 5px;
                    font-family: 'Consolas';
                }
            """)
            
            self.progress_bar.setRange(0, 0)
            
            self.status_timer.start(2000)
            self.log_timer.start(1000)
            
            self.log_message("[START] Go crawler process started in Dark Web mode")
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to start crawler: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to start crawler: {str(e)}")
    
    def stop_crawler(self):
        self.log_message("[STOP] Stopping Go crawler...")
        
        # First, update config to stop crawler gracefully
        self.crawler_manager.stop_crawler()
        
        import time
        time.sleep(2)
        

        if self.go_crawler_process and self.go_crawler_process.state() == QProcess.Running:
            self.log_message("[STOP] Terminating crawler process...")
            self.go_crawler_process.terminate()
            if not self.go_crawler_process.waitForFinished(3000):
                self.log_message("[STOP] Force killing crawler process...")
                self.go_crawler_process.kill()
                self.go_crawler_process.waitForFinished()
        
        # Also kill via taskkill to be sure
        try:
            import subprocess
            subprocess.run(['taskkill', '/F', '/IM', 'phobos-crawler.exe'], 
                         capture_output=True, timeout=5)
            self.log_message("[STOP] Killed any remaining phobos-crawler.exe processes")
        except:
            pass
        
        self.status_timer.stop()
        self.log_timer.stop()
        self.crawler_finished()
    
    def crawler_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Status: IDLE")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #00FF00;
                font-size: 15px;
                font-weight: bold;
                padding: 5px;
                font-family: 'Consolas';
            }
        """)
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        
        self.log_message("[SYSTEM] Go crawler stopped")
        self.status_timer.stop()
        self.log_timer.stop()
    
    def read_crawler_stdout(self):
        if self.go_crawler_process:
            output = bytes(self.go_crawler_process.readAllStandardOutput()).decode('utf-8', errors='ignore')
            for line in output.strip().split('\n'):
                if line.strip():
                    self.go_crawler_logs.append(line.strip())
                    if len(self.go_crawler_logs) > 500:
                        self.go_crawler_logs = self.go_crawler_logs[-500:]
                    # Don't log to system logs, only to crawler logs tab
                    if not self.status_timer.isActive():
                        self.status_timer.start(2000)
                    if not self.log_timer.isActive():
                        self.log_timer.start(1000)
    
    def read_crawler_stderr(self):
        if self.go_crawler_process:
            output = bytes(self.go_crawler_process.readAllStandardError()).decode('utf-8', errors='ignore')
            for line in output.strip().split('\\n'):
                if line.strip():
                    self.go_crawler_logs.append(f"[ERROR] {line.strip()}")
                    if len(self.go_crawler_logs) > 500:
                        self.go_crawler_logs = self.go_crawler_logs[-500:]
                    # Don't log to system logs
    
    def read_crawler_logs(self):
        try:
            db_path = os.path.join(os.path.dirname(__file__), 'databases', 'phobos_index.db')
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1")
                count = cursor.fetchone()[0]
                self.pages_crawled_label.setText(f"Pages Crawled: {count}")
                conn.close()
        except Exception as e:
            pass
    
    def update_crawler_status(self):
        try:
            status = self.crawler_manager.get_status()
            if status.get('running'):
                self.status_label.setText("Status: RUNNING (Dark Web)")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #4EC9B0;
                        font-size: 15px;
                        font-weight: bold;
                        padding: 5px;
                        font-family: 'Consolas';
                    }
                """)
            else:
                if self.start_button.isEnabled() == False:
                    self.crawler_finished()
        except Exception as e:
            self.log_message(f"[ERROR] Status update failed: {str(e)}")
    
    def load_crawler_config(self):
        try:
            settings = self.crawler_manager.get_crawler_settings()
            self.depth_spin.setValue(settings.get('max_depth', 3))
            self.concurrent_spin.setValue(settings.get('concurrent_crawlers', 20))
            self.delay_spin.setValue(settings.get('download_delay', 1.0))
            self.tor_proxy_input.setText(settings.get('tor_proxy', '127.0.0.1:9050'))
        except Exception as e:
            self.log_message(f"[ERROR] Failed to load config: {str(e)}")
    
    def clear_logs(self):
        self.log_display.clear()
        self.log_message("[SYSTEM] Logs cleared")
    
    def load_intelligence_data(self):
        try:
            if os.path.exists(self.intelligence_data_file):
                with open(self.intelligence_data_file, 'r') as f:
                    return json.load(f)
            return {
                'threat_keywords': [],
                'threatening_samples': [],
                'non_threatening_samples': []
            }
        except Exception as e:
            self.log_message(f"[ERROR] Failed to load intelligence data: {str(e)}")
            return {
                'threat_keywords': [],
                'threatening_samples': [],
                'non_threatening_samples': []
            }
    
    def save_intelligence_data(self, data):
        try:
            with open(self.intelligence_data_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.log_message("[SAVE] Intelligence data saved successfully")
            return True
        except Exception as e:
            self.log_message(f"[ERROR] Failed to save intelligence data: {str(e)}")
            return False
    
    def add_keywords(self):
        keywords_text = self.keywords_input.toPlainText().strip()
        if not keywords_text:
            self.log_message("[ERROR] No keywords provided")
            QMessageBox.warning(self, "Warning", "Please enter keywords!")
            return
        
        keywords = [kw.strip() for kw in keywords_text.split('|') if kw.strip()]
        
        if not keywords:
            self.log_message("[ERROR] No valid keywords found in input")
            QMessageBox.warning(self, "Warning", "No valid keywords found!")
            return
        
        keywords_str = ' '.join([f'"{kw}"' for kw in keywords])
        self.log_message(f"[COMMAND] intel add-keywords {keywords_str}")
        self.log_message(f"[INFO] Adding {len(keywords)} keyword(s) to threat intelligence")
        
        data = self.load_intelligence_data()
        existing = set(data.get('threat_keywords', []))
        new_keywords = [kw for kw in keywords if kw not in existing]
        
        data['threat_keywords'] = data.get('threat_keywords', []) + new_keywords
        
        if self.save_intelligence_data(data):
            self.log_message(f"[SUCCESS] Added {len(new_keywords)} new keywords")
            self.keywords_input.clear()
            self.refresh_intelligence_display()
            QMessageBox.information(self, "Success", f"Added {len(new_keywords)} keywords!")
    
    def add_threat_samples(self):
        samples_text = self.threat_input.toPlainText().strip()
        if not samples_text:
            self.log_message("[ERROR] No threat samples provided")
            QMessageBox.warning(self, "Warning", "Please enter threat samples!")
            return
        
        samples = [s.strip() for s in samples_text.split('|') if s.strip()]
        
        if not samples:
            self.log_message("[ERROR] No valid threat samples found in input")
            QMessageBox.warning(self, "Warning", "No valid samples found!")
            return
        
        self.log_message(f"[COMMAND] intel add-threat --count={len(samples)}")
        self.log_message(f"[INFO] Adding {len(samples)} threat sample(s) for training")
        
        data = self.load_intelligence_data()
        data['threatening_samples'] = data.get('threatening_samples', []) + samples
        
        if self.save_intelligence_data(data):
            self.log_message(f"[SUCCESS] Added {len(samples)} threat samples")
            self.threat_input.clear()
            self.refresh_intelligence_display()
            QMessageBox.information(self, "Success", f"Added {len(samples)} threat samples!")
    
    def add_non_threat_samples(self):
        samples_text = self.non_threat_input.toPlainText().strip()
        if not samples_text:
            self.log_message("[ERROR] No non-threat samples provided")
            QMessageBox.warning(self, "Warning", "Please enter non-threat samples!")
            return
        
        samples = [s.strip() for s in samples_text.split('|') if s.strip()]
        
        if not samples:
            self.log_message("[ERROR] No valid non-threat samples found in input")
            QMessageBox.warning(self, "Warning", "No valid samples found!")
            return
        
        self.log_message(f"[COMMAND] intel add-nonthreat --count={len(samples)}")
        self.log_message(f"[INFO] Adding {len(samples)} non-threat sample(s) for training")
        
        data = self.load_intelligence_data()
        data['non_threatening_samples'] = data.get('non_threatening_samples', []) + samples
        
        if self.save_intelligence_data(data):
            self.log_message(f"[SUCCESS] Added {len(samples)} non-threat samples")
            self.non_threat_input.clear()
            self.refresh_intelligence_display()
            QMessageBox.information(self, "Success", f"Added {len(samples)} non-threat samples!")
    
    def refresh_intelligence_display(self):
        self.log_message("[COMMAND] intel refresh")
        self.log_message("[INFO] Refreshing intelligence data display")
        
        data = self.load_intelligence_data()
        
        display_text = ""
        
        display_text += "=" * 80 + "\n"
        display_text += "THREAT KEYWORDS\n"
        display_text += "=" * 80 + "\n"
        display_text += f"Total: {len(data.get('threat_keywords', []))}\n\n"
        for i, keyword in enumerate(data.get('threat_keywords', []), 1):
            display_text += f"{i:3d}. {keyword}\n"
        
        display_text += "\n" + "=" * 80 + "\n"
        display_text += "THREATENING SAMPLES\n"
        display_text += "=" * 80 + "\n"
        display_text += f"Total: {len(data.get('threatening_samples', []))}\n\n"
        for i, sample in enumerate(data.get('threatening_samples', []), 1):
            display_text += f"{i:3d}. {sample}\n"
        
        display_text += "\n" + "=" * 80 + "\n"
        display_text += "NON-THREATENING SAMPLES\n"
        display_text += "=" * 80 + "\n"
        display_text += f"Total: {len(data.get('non_threatening_samples', []))}\n\n"
        for i, sample in enumerate(data.get('non_threatening_samples', []), 1):
            display_text += f"{i:3d}. {sample}\n"
        
        self.intel_display.setPlainText(display_text)
    
    def retrain_analyzer(self):
        self.log_message("[COMMAND] intel retrain")
        self.log_message("[INFO] Requesting analyzer retrain confirmation")
        
        reply = QMessageBox.question(
            self, 
            "Retrain Analyzer", 
            "This will retrain the threat analyzer with updated data. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log_message("[INFO] Retraining analyzer with updated intelligence data...")
            try:
                from scripts.analyzer import IntelligenceAnalyzer
                analyzer = IntelligenceAnalyzer()
                
                if analyzer.neural_analyzer:
                    neural_result = analyzer.retrain_neural_model()
                    if neural_result:
                        self.log_message("[SUCCESS] Neural network retrained successfully")
                    else:
                        self.log_message("[WARNING] Neural network retrain failed")
                
                self.log_message("[SUCCESS] Analyzer retrained successfully")
                QMessageBox.information(self, "Success", "Analyzer retrained successfully!")
            except Exception as e:
                self.log_message(f"[ERROR] Failed to retrain analyzer: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to retrain: {str(e)}")
        else:
            self.log_message("[INFO] Retrain cancelled")
    
    def show_model_metrics(self):
        self.log_message("[COMMAND] intel metrics")
        self.log_message("[INFO] Loading neural network model metrics")
        
        try:
            from scripts.analyzer import IntelligenceAnalyzer
            analyzer = IntelligenceAnalyzer()
            
            if not analyzer.neural_analyzer:
                self.log_message("[WARNING] Neural network not available")
                QMessageBox.information(self, "Model Metrics", "Neural network not available")
                return
            
            metrics = analyzer.get_neural_model_info()
            self.log_message("[SUCCESS] Model metrics loaded successfully")
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Neural Network Model Metrics")
            dialog.setMinimumWidth(500)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1a1a1a;
                }
                QLabel {
                    color: #CCCCCC;
                    font-family: 'Consolas';
                    font-size: 12px;
                }
            """)
            
            layout = QVBoxLayout()
            dialog.setLayout(layout)
            
            header = QLabel("Neural Network Performance Metrics")
            header.setStyleSheet("""
                QLabel {
                    color: #00FFFF;
                    font-weight: bold;
                    font-size: 16px;
                    padding: 10px;
                    background-color: #0a0a0a;
                    border-bottom: 2px solid #00FFFF;
                }
            """)
            layout.addWidget(header)
            
            metrics_text = f"""
Last Training: {metrics.get('timestamp', 'N/A')}

Training Accuracy:     {metrics.get('train_accuracy', 0):.3f}
Testing Accuracy:      {metrics.get('test_accuracy', 0):.3f}

Total Training Samples:    {metrics.get('total_samples', 0)}
Threat Samples:            {metrics.get('threat_samples', 0)}
Safe Samples:              {metrics.get('safe_samples', 0)}
Historical Samples:        {metrics.get('historical_samples', 0)}

Training Iterations:       {metrics.get('iterations', 0)}

Model Type: Multi-Layer Perceptron (MLP)
Hidden Layers: 128 → 64 → 32 neurons
Activation: ReLU
Optimizer: Adam
Learning Rate: Adaptive
            """
            
            info_label = QLabel(metrics_text)
            info_label.setStyleSheet("""
                QLabel {
                    color: #00FF00;
                    padding: 20px;
                    font-size: 13px;
                    background-color: #0a0a0a;
                }
            """)
            layout.addWidget(info_label)
            
            close_btn = QPushButton("CLOSE")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: #FFFFFF;
                    font-size: 12px;
                    padding: 10px;
                    border: 1px solid #555555;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
            """)
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load metrics: {str(e)}")
    
    def get_all_reports(self):
        reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
        if not os.path.exists(reports_dir):
            return []
        
        reports = []
        for filename in os.listdir(reports_dir):
            if filename.endswith('.json') and filename != 'overall_report.json':
                filepath = os.path.join(reports_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        report = json.load(f)
                        report['filename'] = filename
                        reports.append(report)
                except:
                    pass
        
        reports.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return reports
    
    def create_briefing_summary(self, reports):
        if not reports:
            return {
                'total_pages': 0,
                'avg_threat': 0.0,
                'high_threats': 0,
                'medium_threats': 0,
                'low_threats': 0,
                'total_entities': 0,
                'top_keywords': [],
                'reports': [],
                'alerts': []
            }
        
        total_threat = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        all_keywords = []
        total_entities = 0
        alerts = []
        
        for report in reports:
            threat_score = report.get('threat_score', 0)
            total_threat += threat_score
            
            if threat_score >= 0.5:
                high_count += 1
            elif threat_score >= 0.3:
                medium_count += 1
            else:
                low_count += 1
            
            entities = report.get('entities', {})
            total_entities += len(entities.get('persons', [])) + len(entities.get('organizations', [])) + len(entities.get('locations', []))
            all_keywords.extend(entities.get('keywords', []))
            
            # Collect alerts for high-threat reports
            alert_info = report.get('alert_info', {})
            if alert_info.get('is_high_threat', False):
                alerts.append({
                    'url': report.get('url', 'N/A'),
                    'threat_score': threat_score,
                    'threat_level': alert_info.get('threat_level', 'HIGH'),
                    'matched_keywords': alert_info.get('matched_keywords', []),
                    'threat_sentences': alert_info.get('threat_sentences', []),
                    'alert_reasons': alert_info.get('alert_reasons', [])
                })
        
        keyword_freq = {}
        for kw in all_keywords:
            keyword_freq[kw] = keyword_freq.get(kw, 0) + 1
        
        top_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_pages': len(reports),
            'avg_threat': round(total_threat / len(reports), 3) if reports else 0.0,
            'high_threats': high_count,
            'medium_threats': medium_count,
            'low_threats': low_count,
            'total_entities': total_entities,
            'top_keywords': [kw[0] for kw in top_keywords],
            'reports': reports,
            'alerts': alerts
        }
    
    def refresh_briefings(self):
        self.log_message("[COMMAND] report refresh")
        self.log_message("[INFO] Refreshing intelligence briefings list")
        
        self.briefings_list.clear()
        reports = self.get_all_reports()
        
        if not reports:
            item = QListWidgetItem("No reports found")
            item.setData(Qt.UserRole, None)
            self.briefings_list.addItem(item)
            self.briefing_display.setPlainText("No reports available. Run the crawler to generate reports.")
            return
        
        self.briefing_data = []
        
        for i in range(0, len(reports), 10):
            batch = reports[i:i+10]
            briefing = self.create_briefing_summary(batch)
            briefing['batch_index'] = i // 10
            briefing['start_index'] = i
            briefing['end_index'] = min(i + 10, len(reports))
            self.briefing_data.append(briefing)
            
            item_text = f"Briefing #{briefing['batch_index'] + 1}\n"
            item_text += f"Reports: {briefing['start_index'] + 1}-{briefing['end_index']}\n"
            item_text += f"Avg Threat: {briefing['avg_threat']}\n"
            item_text += f"High: {briefing['high_threats']} | Med: {briefing['medium_threats']} | Low: {briefing['low_threats']}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, briefing)
            self.briefings_list.addItem(item)
        
        self.log_message(f"[INFO] Loaded {len(self.briefing_data)} intelligence briefings")
    
    def refresh_crawled_urls(self):
        """Load and display crawled URLs from phobos_index.db"""
        try:
            db_path = os.path.join(os.path.dirname(__file__), 'databases', 'phobos_index.db')
            
            if not os.path.exists(db_path):
                self.log_message("[ERROR] phobos_index.db not found")
                self.crawled_stats_label.setText("Database not found")
                return
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get stats
            cursor.execute("SELECT COUNT(*) FROM pages")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1")
            active = cursor.fetchone()[0]
            
            self.crawled_stats_label.setText(f"Total Crawled: {total} | Active: {active}")
            
            # Get pages
            cursor.execute("""
                SELECT id, url, title, domain, is_active, crawled_at
                FROM pages
                ORDER BY crawled_at DESC
                LIMIT 1000
            """)
            
            rows = cursor.fetchall()
            
            self.crawled_urls_table.setRowCount(len(rows))
            
            for i, row in enumerate(rows):
                page_id, url, title, domain, is_active, crawled_at = row
                
                # ID
                self.crawled_urls_table.setItem(i, 0, QTableWidgetItem(str(page_id)))
                
                # URL (truncate if too long)
                url_display = url[:80] + "..." if len(url) > 80 else url
                self.crawled_urls_table.setItem(i, 1, QTableWidgetItem(url_display))
                
                # Title
                title_display = (title[:50] + "...") if title and len(title) > 50 else (title or "N/A")
                self.crawled_urls_table.setItem(i, 2, QTableWidgetItem(title_display))
                
                # Domain
                self.crawled_urls_table.setItem(i, 3, QTableWidgetItem(domain or "N/A"))
                
                # Status
                status = "ACTIVE" if is_active else "INACTIVE"
                status_item = QTableWidgetItem(status)
                if is_active:
                    status_item.setForeground(QColor("#4EC9B0"))
                else:
                    status_item.setForeground(QColor("#666666"))
                self.crawled_urls_table.setItem(i, 4, status_item)
                
                # Crawled At
                self.crawled_urls_table.setItem(i, 5, QTableWidgetItem(crawled_at or "N/A"))
            
            conn.close()
            
            self.log_message(f"[INFO] Loaded {len(rows)} crawled URLs from database")
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to load crawled URLs: {str(e)}")
            self.crawled_stats_label.setText(f"Error: {str(e)}")
    
    def display_briefing_details(self, item):
        briefing = item.data(Qt.UserRole)
        if not briefing:
            return
        
        briefing_id = briefing.get('batch_index', 0) + 1
        self.log_message(f"[COMMAND] report refresh --view --id={briefing_id}")
        self.log_message(f"[INFO] Loading intelligence briefing #{briefing_id}")
        
        self.current_briefing = briefing
        self.briefing_title.setText(f"Intelligence Briefing #{briefing['batch_index'] + 1} (Reports {briefing['start_index'] + 1}-{briefing['end_index']})")
        self.log_message(f"[SUCCESS] Briefing #{briefing_id} loaded successfully")
        
        html_text = '<pre style="color: #ffffff; font-family: Consolas; font-size: 15px;">'
        html_text += "=" * 90 + "\n"
        html_text += f"INTELLIGENCE BRIEFING #{briefing['batch_index'] + 1}\n"
        html_text += "=" * 90 + "\n\n"
        
        html_text += '<span style="color: #00FFFF;">'
        html_text += "SUMMARY STATISTICS\n"
        html_text += "-" * 90 + "\n"
        html_text += f"Total Pages Analyzed:    {briefing['total_pages']}\n"
        html_text += f"Average Threat Score:    {briefing['avg_threat']}\n"
        html_text += f"High Threat Pages:       {briefing['high_threats']}\n"
        html_text += f"Medium Threat Pages:     {briefing['medium_threats']}\n"
        html_text += f"Low Threat Pages:        {briefing['low_threats']}\n"
        html_text += f"Total Entities Found:    {briefing['total_entities']}\n"
        html_text += '</span>'
        html_text += "\n"
        
        # Display threat alerts section
        alerts = briefing.get('alerts', [])
        if alerts:
            html_text += "\n"
            html_text += '<span style="color: #FF0000; font-weight: bold;">'
            html_text += "=" * 90 + "\n"
            html_text += f"SECURITY ALERTS - {len(alerts)} HIGH-THREAT PAGE(S) DETECTED\n"
            html_text += "=" * 90 + "\n"
            html_text += '</span>'
            html_text += "\n"
            
            for idx, alert in enumerate(alerts, 1):
                threat_color = "#FF0000" if alert['threat_level'] == "CRITICAL" else "#FFA500"
                html_text += f'<span style="color: {threat_color}; font-weight: bold;">'
                html_text += f"[ALERT #{idx}] {alert['threat_level']} THREAT - Score: {alert['threat_score']}\n"
                html_text += '</span>'
                html_text += "-" * 90 + "\n"
                html_text += f"URL: {alert['url']}\n\n"
                
                # Display alert reasons
                if alert['alert_reasons']:
                    html_text += '<span style="color: #FFFF00;">'
                    html_text += "Alert Triggers:\n"
                    html_text += '</span>'
                    for reason in alert['alert_reasons']:
                        html_text += f"  • {reason}\n"
                    html_text += "\n"
                
                # Display matched keywords
                if alert['matched_keywords']:
                    html_text += '<span style="color: #FF6B6B;">'
                    html_text += f"Matched Keywords ({len(alert['matched_keywords'])}): "
                    html_text += '</span>'
                    html_text += f"{', '.join(alert['matched_keywords'][:10])}\n"
                    if len(alert['matched_keywords']) > 10:
                        html_text += f"  (+{len(alert['matched_keywords']) - 10} more)\n"
                    html_text += "\n"
                
                # Display threat sentences
                if alert['threat_sentences']:
                    html_text += '<span style="color: #FFA500;">'
                    html_text += "Suspicious Content Detected:\n"
                    html_text += '</span>'
                    for i, sentence in enumerate(alert['threat_sentences'][:3], 1):
                        html_text += f"  {i}. \"{sentence}\"\n"
                    html_text += "\n"
                
                html_text += "=" * 90 + "\n\n"
        
        if briefing['top_keywords']:
            html_text += "TOP THREAT KEYWORDS\n"
            html_text += "-" * 90 + "\n"
            for i, kw in enumerate(briefing['top_keywords'], 1):
                html_text += f"{i}. {kw}\n"
            html_text += "\n"
        
        html_text += "=" * 90 + "\n"
        html_text += "DETAILED REPORTS\n"
        html_text += "=" * 90 + "\n\n"
        
        for i, report in enumerate(briefing['reports'], briefing['start_index'] + 1):
            threat_score = report.get('threat_score', 0)
            
            # Highlight high-threat reports
            if threat_score >= 0.6:
                html_text += '<span style="color: #FF0000;">'
                html_text += f"[Report #{i}] ⚠️ HIGH THREAT\n"
                html_text += '</span>'
            else:
                html_text += f"[Report #{i}]\n"
            
            html_text += "-" * 90 + "\n"
            html_text += f"URL:          {report.get('url', 'N/A')}\n"
            html_text += f"Timestamp:    {report.get('timestamp', 'N/A')}\n"
            
            # Color-code threat score
            if threat_score >= 0.8:
                html_text += '<span style="color: #FF0000; font-weight: bold;">'
                html_text += f"Threat Score: {threat_score} [CRITICAL]\n"
                html_text += '</span>'
            elif threat_score >= 0.6:
                html_text += '<span style="color: #FFA500; font-weight: bold;">'
                html_text += f"Threat Score: {threat_score} [HIGH]\n"
                html_text += '</span>'
            else:
                html_text += f"Threat Score: {threat_score}\n"
            
            entities = report.get('entities', {})
            if entities.get('persons'):
                html_text += f"Persons:      {', '.join(entities['persons'][:5])}\n"
            if entities.get('organizations'):
                html_text += f"Organizations: {', '.join(entities['organizations'][:5])}\n"
            if entities.get('locations'):
                html_text += f"Locations:    {', '.join(entities['locations'][:5])}\n"
            if entities.get('keywords'):
                html_text += '<span style="color: #FF6B6B;">'
                html_text += f"Keywords:     {', '.join(entities['keywords'])}\n"
                html_text += '</span>'
            
            summary = report.get('summary', '')
            if summary:
                html_text += f"\nSummary:\n{summary[:300]}...\n"
            
            html_text += "\n" + "=" * 90 + "\n\n"
        
        html_text += '</pre>'
        self.briefing_display.setHtml(html_text)
        self.log_message(f"[VIEW] Displaying briefing #{briefing['batch_index'] + 1} with {len(alerts)} alert(s)")
    
    def export_current_briefing(self):
        if not hasattr(self, 'current_briefing'):
            self.log_message("[ERROR] No briefing selected for export")
            QMessageBox.warning(self, "Warning", "Please select a briefing first!")
            return
        
        briefing = self.current_briefing
        briefing_id = briefing['batch_index'] + 1
        filename = f"briefing_{briefing_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(os.path.dirname(__file__), 'reports', filename)
        
        self.log_message(f"[COMMAND] report export --id={briefing_id} --output={filename}")
        self.log_message(f"[INFO] Exporting briefing #{briefing_id} to {filename}")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.briefing_display.toPlainText())
            self.log_message(f"[SUCCESS] Briefing exported to {filename}")
            QMessageBox.information(self, "Success", f"Briefing exported to:\n{filepath}")
        except Exception as e:
            self.log_message(f"[ERROR] Failed to export briefing: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")
    
    def create_database_leaks_tab(self):
        leaks_widget = QWidget()
        leaks_layout = QVBoxLayout()
        leaks_widget.setLayout(leaks_layout)
        
        header_layout = QHBoxLayout()
        
        title = QLabel("DATABASE LEAK INTELLIGENCE")
        title.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 11px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px;
                background-color: #2b2b2b;
                border-bottom: 1px solid #3a3a3a;
            }
        """)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_leaks_btn = QPushButton("REFRESH LEAKS")
        refresh_leaks_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                font-size: 10px;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px 12px;
                border: 1px solid #2a2a2a;
                border-radius: 0px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        refresh_leaks_btn.clicked.connect(self.refresh_database_leaks)
        header_layout.addWidget(refresh_leaks_btn)
        
        export_leaks_btn = QPushButton("EXPORT CSV")
        export_leaks_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                font-size: 10px;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px 12px;
                border: 1px solid #2a2a2a;
                border-radius: 0px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        export_leaks_btn.clicked.connect(self.export_leaks_csv)
        header_layout.addWidget(export_leaks_btn)
        
        leaks_layout.addLayout(header_layout)
        
        filter_group = QGroupBox("FILTERS")
        filter_group.setStyleSheet("""
            QGroupBox {
                color: #999999;
                font-size: 10px;
                font-family: 'Segoe UI', 'Arial';
                font-weight: normal;
                border: 1px solid #2a2a2a;
                margin-top: 8px;
                padding-top: 10px;
                background-color: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 6px;
                color: #cccccc;
            }
        """)
        filter_layout = QHBoxLayout()
        filter_group.setLayout(filter_layout)
        
        filter_layout.addWidget(QLabel("Risk:"))
        self.leak_risk_filter = QComboBox()
        self.leak_risk_filter.addItems(["ALL", "CRITICAL_THREAT", "HIGH_THREAT", "MEDIUM_THREAT", "STRATEGIC_ADVANTAGE", "INTELLIGENCE_VALUE", "INTERNATIONAL_CONCERN"])
        self.leak_risk_filter.currentTextChanged.connect(self.refresh_database_leaks)
        self.leak_risk_filter.setStyleSheet("""
            QComboBox {
                background-color: #252525;
                color: #ffffff;
                border: 1px solid #2a2a2a;
                padding: 4px;
                font-size: 10px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #252525;
                color: #ffffff;
                selection-background-color: #3a3a3a;
            }
        """)
        filter_layout.addWidget(self.leak_risk_filter)
        
        filter_layout.addWidget(QLabel("Country:"))
        self.leak_country_filter = QComboBox()
        self.leak_country_filter.addItems(["ALL", "india", "pakistan", "bangladesh", "unknown"])
        self.leak_country_filter.currentTextChanged.connect(self.refresh_database_leaks)
        self.leak_country_filter.setStyleSheet(self.leak_risk_filter.styleSheet())
        filter_layout.addWidget(self.leak_country_filter)
        
        filter_layout.addWidget(QLabel("Threat to India:"))
        self.leak_threat_filter = QComboBox()
        self.leak_threat_filter.addItems(["ALL", "YES", "NO"])
        self.leak_threat_filter.currentTextChanged.connect(self.refresh_database_leaks)
        self.leak_threat_filter.setStyleSheet(self.leak_risk_filter.styleSheet())
        filter_layout.addWidget(self.leak_threat_filter)
        
        filter_layout.addStretch()
        
        leaks_layout.addWidget(filter_group)
        
        self.leaks_table = QTableWidget()
        self.leaks_table.setColumnCount(9)
        self.leaks_table.setHorizontalHeaderLabels([
            "ID", "URL", "Origin", "Risk", "Sensitive Level", 
            "Data Categories", "PII Types", "Leak Indicators", "Detected"
        ])
        self.leaks_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a0a;
                color: #cccccc;
                gridline-color: #2a2a2a;
                border: 1px solid #2a2a2a;
                font-size: 10px;
                font-family: 'Consolas', 'Courier New';
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #1a1a1a;
            }
            QTableWidget::item:selected {
                background-color: #3a3a3a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #ffffff;
                padding: 6px;
                border: 1px solid #1a1a1a;
                font-size: 10px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
            }
        """)
        self.leaks_table.horizontalHeader().setStretchLastSection(True)
        self.leaks_table.verticalHeader().setVisible(False)
        self.leaks_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.leaks_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.leaks_table.doubleClicked.connect(self.show_leak_details)
        
        leaks_layout.addWidget(self.leaks_table)
        
        stats_label = QLabel("Total Leaks: 0 | Threats to India: 0 | Strategic Advantages: 0")
        stats_label.setStyleSheet("""
            QLabel {
                color: #999999;
                font-size: 10px;
                padding: 4px;
                background-color: #1a1a1a;
                border-top: 1px solid #2a2a2a;
            }
        """)
        self.leak_stats_label = stats_label
        leaks_layout.addWidget(stats_label)
        
        self.tabs.addTab(leaks_widget, "DATABASE LEAKS")
        
        self.refresh_database_leaks()
    
    def refresh_database_leaks(self):
        try:
            conn = sqlite3.connect('databases/phobos_analysis.db')
            cursor = conn.cursor()
            
            query = "SELECT id, url, origin_country, risk_classification, sensitive_level, data_categories, pii_types, leak_indicators, analyzed_at FROM threat_analysis WHERE leak_detected = 1"
            conditions = []
            params = []
            
            risk_filter = self.leak_risk_filter.currentText()
            if risk_filter != "ALL":
                conditions.append("risk_classification = ?")
                params.append(risk_filter)
            
            country_filter = self.leak_country_filter.currentText()
            if country_filter != "ALL":
                conditions.append("origin_country = ?")
                params.append(country_filter)
            
            threat_filter = self.leak_threat_filter.currentText()
            if threat_filter == "YES":
                conditions.append("threat_to_india = 1")
            elif threat_filter == "NO":
                conditions.append("threat_to_india = 0")
            
            if conditions:
                query += " AND " + " AND ".join(conditions)
            
            query += " ORDER BY analyzed_at DESC"
            
            results = cursor.execute(query, params).fetchall()
            
            self.leaks_table.setRowCount(len(results))
            
            for row_idx, row in enumerate(results):
                leak_id, url, origin, risk, sensitive, categories, pii, indicators, detected = row
                
                self.leaks_table.setItem(row_idx, 0, QTableWidgetItem(str(leak_id)))
                
                url_item = QTableWidgetItem(url[:60] + "..." if len(url) > 60 else url)
                url_item.setToolTip(url)
                self.leaks_table.setItem(row_idx, 1, url_item)
                
                origin_item = QTableWidgetItem(origin or "unknown")
                if origin == "india":
                    origin_item.setForeground(QColor("#ff4444"))
                elif origin in ["pakistan", "bangladesh"]:
                    origin_item.setForeground(QColor("#44ff44"))
                self.leaks_table.setItem(row_idx, 2, origin_item)
                
                risk_item = QTableWidgetItem(risk or "UNKNOWN")
                if "THREAT" in (risk or ""):
                    risk_item.setForeground(QColor("#ff4444"))
                elif "ADVANTAGE" in (risk or ""):
                    risk_item.setForeground(QColor("#44ff44"))
                self.leaks_table.setItem(row_idx, 3, risk_item)
                
                self.leaks_table.setItem(row_idx, 4, QTableWidgetItem(sensitive or ""))
                
                try:
                    cats = json.loads(categories) if categories else []
                    self.leaks_table.setItem(row_idx, 5, QTableWidgetItem(", ".join(cats)))
                except:
                    self.leaks_table.setItem(row_idx, 5, QTableWidgetItem(""))
                
                try:
                    pii_list = json.loads(pii) if pii else []
                    self.leaks_table.setItem(row_idx, 6, QTableWidgetItem(", ".join(pii_list)))
                except:
                    self.leaks_table.setItem(row_idx, 6, QTableWidgetItem(""))
                
                try:
                    ind_list = json.loads(indicators) if indicators else []
                    self.leaks_table.setItem(row_idx, 7, QTableWidgetItem(", ".join(ind_list[:3])))
                except:
                    self.leaks_table.setItem(row_idx, 7, QTableWidgetItem(""))
                
                self.leaks_table.setItem(row_idx, 8, QTableWidgetItem(detected[:19] if detected else ""))
            
            total_leaks = len(results)
            threats = cursor.execute("SELECT COUNT(*) FROM threat_analysis WHERE leak_detected = 1 AND threat_to_india = 1").fetchone()[0]
            advantages = cursor.execute("SELECT COUNT(*) FROM threat_analysis WHERE leak_detected = 1 AND origin_country IN ('pakistan', 'bangladesh')").fetchone()[0]
            
            self.leak_stats_label.setText(f"Total Leaks: {total_leaks} | Threats to India: {threats} | Strategic Advantages: {advantages}")
            
            conn.close()
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to refresh leaks: {str(e)}")
    
    def show_leak_details(self):
        try:
            row = self.leaks_table.currentRow()
            leak_id = int(self.leaks_table.item(row, 0).text())
            
            conn = sqlite3.connect('databases/phobos_analysis.db')
            cursor = conn.cursor()
            
            result = cursor.execute("""
                SELECT url, origin_country, risk_classification, sensitive_level, 
                       data_categories, pii_types, leak_indicators, json_report_path
                FROM threat_analysis WHERE id = ?
            """, (leak_id,)).fetchone()
            
            if result:
                url, origin, risk, sensitive, cats, pii, indicators, report_path = result
                
                details = f"URL: {url}\n\n"
                details += f"Origin Country: {origin}\n"
                details += f"Risk Classification: {risk}\n"
                details += f"Sensitive Level: {sensitive}\n\n"
                details += f"Data Categories: {cats}\n"
                details += f"PII Types: {pii}\n"
                details += f"Leak Indicators: {indicators}\n\n"
                
                if report_path:
                    details += f"Full Report: {report_path}"
                
                msg = QMessageBox()
                msg.setWindowTitle("Leak Details")
                msg.setText(details)
                msg.setStyleSheet("""
                    QMessageBox {
                        background-color: #1a1a1a;
                        color: #ffffff;
                    }
                    QLabel {
                        color: #ffffff;
                        font-family: 'Consolas';
                        font-size: 10px;
                    }
                    QPushButton {
                        background-color: #3a3a3a;
                        color: #ffffff;
                        padding: 6px 12px;
                        border: 1px solid #2a2a2a;
                    }
                """)
                msg.exec_()
            
            conn.close()
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to show leak details: {str(e)}")
    
    def export_leaks_csv(self):
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"leak_export_{timestamp}.csv"
            
            conn = sqlite3.connect('databases/phobos_analysis.db')
            cursor = conn.cursor()
            
            results = cursor.execute("""
                SELECT id, url, origin_country, risk_classification, sensitive_level,
                       data_categories, pii_types, leak_indicators, analyzed_at
                FROM threat_analysis WHERE leak_detected = 1
                ORDER BY analyzed_at DESC
            """).fetchall()
            
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "URL", "Origin", "Risk", "Sensitive Level", "Data Categories", "PII Types", "Leak Indicators", "Detected"])
                writer.writerows(results)
            
            conn.close()
            
            self.log_message(f"[SUCCESS] Exported {len(results)} leaks to {filename}")
            QMessageBox.information(self, "Export Complete", f"Exported {len(results)} leaks to {filename}")
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to export leaks: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")
    
    def create_profiling_tab(self):
        """Create the PROFILING tab for person intelligence"""
        profiling_widget = QWidget()
        profiling_layout = QVBoxLayout()
        profiling_widget.setLayout(profiling_layout)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("PERSON PROFILING")
        title.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 11px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px;
                background-color: #2b2b2b;
                border-bottom: 1px solid #3a3a3a;
            }
        """)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_profiles_btn = QPushButton("REFRESH PROFILES")
        refresh_profiles_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                font-size: 10px;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px 12px;
                border: 1px solid #2a2a2a;
                border-radius: 0px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #505050;
                border: 1px solid #4EC9B0;
            }
        """)
        refresh_profiles_btn.clicked.connect(self.refresh_profiles)
        header_layout.addWidget(refresh_profiles_btn)
        
        export_profile_btn = QPushButton("EXPORT PROFILE")
        export_profile_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                font-size: 10px;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px 12px;
                border: 1px solid #2a2a2a;
                border-radius: 0px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #505050;
                border: 1px solid #dcdcaa;
            }
        """)
        export_profile_btn.clicked.connect(self.export_current_profile)
        header_layout.addWidget(export_profile_btn)
        
        profiling_layout.addLayout(header_layout)
        
        # Main content area
        content_layout = QHBoxLayout()
        
        # Left sidebar - Person list
        left_panel = QVBoxLayout()
        
        search_label = QLabel("SEARCH PERSON:")
        search_label.setStyleSheet("""
            QLabel {
                color: #bbbbbb;
                font-size: 10px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
            }
        """)
        left_panel.addWidget(search_label)
        
        self.person_search = QLineEdit()
        self.person_search.setPlaceholderText("Type person name...")
        self.person_search.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3a3a3a;
                padding: 6px;
                font-family: 'Consolas', 'Courier New';
                font-size: 10px;
                selection-background-color: #264f78;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        self.person_search.textChanged.connect(self.search_persons)
        left_panel.addWidget(self.person_search)
        
        persons_label = QLabel("PROFILED PERSONS:")
        persons_label.setStyleSheet("""
            QLabel {
                color: #bbbbbb;
                font-size: 10px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
                padding-top: 10px;
            }
        """)
        left_panel.addWidget(persons_label)
        
        self.persons_list = QListWidget()
        self.persons_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3a3a3a;
                font-family: 'Consolas', 'Courier New';
                font-size: 12px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #264f78;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
            }
        """)
        self.persons_list.itemClicked.connect(self.display_person_profile)
        left_panel.addWidget(self.persons_list)
        
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMaximumWidth(350)
        
        content_layout.addWidget(left_widget)
        
        # Right panel - Person intelligence briefing
        right_panel = QVBoxLayout()
        
        self.profile_title = QLabel("Select a person to view intelligence profile")
        self.profile_title.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 11px;
                font-weight: normal;
                font-family: 'Segoe UI', 'Arial';
                padding: 6px;
                background-color: #2b2b2b;
                border-bottom: 1px solid #3a3a3a;
            }
        """)
        right_panel.addWidget(self.profile_title)
        
        self.profile_display = QTextEdit()
        self.profile_display.setReadOnly(True)
        self.profile_display.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #ffffff;
                font-family: 'Consolas', 'Courier New';
                font-size: 15px;
                font-weight: normal;
                border: none;
                padding: 10px;
                selection-background-color: #264f78;
            }
        """)
        right_panel.addWidget(self.profile_display)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        
        content_layout.addWidget(right_widget)
        
        profiling_layout.addLayout(content_layout)
        
        self.tabs.addTab(profiling_widget, "PROFILING")
        
        # Initialize profiler
        try:
            from scripts.person_profiler import PersonProfiler
            self.profiler = PersonProfiler()
            self.log_message("[PROFILER] Person profiling system ready")
        except Exception as e:
            self.log_message(f"[ERROR] Failed to initialize profiler: {str(e)}")
            self.profiler = None
    
    def refresh_profiles(self):
        """Refresh the list of profiled persons"""
        self.log_message("[COMMAND] profile refresh")
        self.log_message("[INFO] Refreshing person profiles list")
        
        if not self.profiler:
            self.log_message("[ERROR] Profiler not initialized")
            return
        
        self.persons_list.clear()
        
        try:
            persons = self.profiler.get_all_persons()
            
            if not persons:
                item = QListWidgetItem("No persons profiled yet")
                item.setData(Qt.UserRole, None)
                self.persons_list.addItem(item)
                self.profile_display.setPlainText("No person profiles available.\\n\\nRun the crawler to start profiling persons mentioned in web pages.")
                return
            
            # Sort by total mentions (descending)
            persons_sorted = sorted(persons, key=lambda x: x['total_mentions'], reverse=True)
            
            for person in persons_sorted:
                item = QListWidgetItem(person['name'])
                item.setData(Qt.UserRole, person['name'])
                self.persons_list.addItem(item)
            
            self.log_message(f"[PROFILER] Loaded {len(persons)} person profiles")
        
        except Exception as e:
            self.log_message(f"[ERROR] Failed to refresh profiles: {str(e)}")
    
    def search_persons(self, query):
        """Search persons by name"""
        if not self.profiler or not query:
            self.refresh_profiles()
            return
        
        self.log_message(f"[COMMAND] profile search --query=\"{query}\"")
        self.log_message(f"[INFO] Searching for persons matching: {query}")
        
        self.persons_list.clear()
        
        try:
            results = self.profiler.search_persons(query)
            
            if not results:
                item = QListWidgetItem(f"No persons found matching '{query}'")
                item.setData(Qt.UserRole, None)
                self.persons_list.addItem(item)
                self.log_message(f"[INFO] No results found for query: {query}")
                return
            
            self.log_message(f"[SUCCESS] Found {len(results)} person(s) matching query")
            
            for person in results:
                item = QListWidgetItem(person['name'])
                item.setData(Qt.UserRole, person['name'])
                self.persons_list.addItem(item)
        
        except Exception as e:
            self.log_message(f"[ERROR] Search failed: {str(e)}")
    
    def display_person_profile(self, item):
        """Display detailed intelligence profile for selected person"""
        person_name = item.data(Qt.UserRole)
        if not person_name:
            return
        
        self.log_message(f"[COMMAND] profile search --query=\"{person_name}\" --view")
        self.log_message(f"[INFO] Loading intelligence profile for: {person_name}")
        
        try:
            briefing = self.profiler.generate_person_intelligence_briefing(person_name)
            
            if not briefing:
                self.profile_display.setPlainText(f"No profile data for {person_name}")
                self.log_message(f"[WARNING] No profile data found for {person_name}")
                return
            
            self.log_message(f"[SUCCESS] Profile loaded successfully")
            self.current_profile = briefing
            self.profile_title.setText(f"Intelligence Profile: {person_name}")
            
            # Generate HTML formatted profile
            html_text = '<pre style="color: #ffffff; font-family: Consolas; font-size: 15px;">'
            html_text += "=" * 90 + "\n"
            html_text += f"PERSON INTELLIGENCE PROFILE\n"
            html_text += "=" * 90 + "\n\n"
            
            html_text += '<span style="color: #00FFFF; font-weight: bold;">'
            html_text += f"NAME: {person_name}\n"
            html_text += '</span>'
            html_text += "\n"
            
            # Profile Summary
            summary = briefing['profile_summary']
            html_text += '<span style="color: #00FFFF;">'
            html_text += "PROFILE SUMMARY\n"
            html_text += "-" * 90 + "\n"
            html_text += f"Total Mentions:      {summary['total_mentions']}\n"
            html_text += f"First Seen:          {summary['first_seen'][:19]}\n"
            html_text += f"Last Seen:           {summary['last_seen'][:19]}\n"
            html_text += f"URLs Referenced:     {summary['urls_count']}\n"
            html_text += f"Activities Logged:   {summary['activities_count']}\n"
            
            if summary.get('titles'):
                html_text += f"Titles:              {', '.join(summary['titles'])}\n"
            
            html_text += '</span>'
            html_text += "\n"
            
            # Activity Analysis
            activity_analysis = briefing['activity_analysis']
            html_text += '<span style="color: #FFD700;">'
            html_text += "ACTIVITY ANALYSIS\n"
            html_text += "-" * 90 + "\n"
            html_text += f"Most Common Activity: {activity_analysis['most_common_activity']}\n"
            html_text += "\nActivity Breakdown:\n"
            html_text += '</span>'
            
            for act_type, count in activity_analysis['activity_breakdown'].items():
                html_text += f"  • {act_type.title()}: {count} time(s)\n"
            
            # Content Samples
            if activity_analysis.get('content_samples'):
                html_text += "\n"
                html_text += '<span style="color: #FFA500;">'
                html_text += "CONTENT SAMPLES (What they said/posted):\n"
                html_text += "-" * 90 + "\n"
                html_text += '</span>'
                
                for i, content in enumerate(activity_analysis['content_samples'], 1):
                    if content:
                        html_text += f'{i}. "{content[:200]}..."\n\n'
            
            # Keywords
            if briefing.get('keywords'):
                html_text += "\n"
                html_text += '<span style="color: #FF6B6B;">'
                html_text += "ASSOCIATED KEYWORDS:\n"
                html_text += "-" * 90 + "\n"
                html_text += f"{', '.join(briefing['keywords'])}\n"
                html_text += '</span>'
                html_text += "\n"
            
            # Timeline
            html_text += "\n"
            html_text += "=" * 90 + "\n"
            html_text += "ACTIVITY TIMELINE (Recent 15)\n"
            html_text += "=" * 90 + "\n\n"
            
            for entry in briefing['timeline']:
                html_text += '<span style="color: #00FFFF;">'
                html_text += f"[{entry['timestamp'][:19]}]\n"
                html_text += '</span>'
                html_text += f"URL: {entry['url']}\n"
                html_text += f"Activity: {entry['activities']}\n"
                html_text += f"Context: {entry['preview']}...\n"
                html_text += "-" * 90 + "\n"
            
            # All URLs
            html_text += "\n"
            html_text += "=" * 90 + "\n"
            html_text += "ALL REFERENCED URLS\n"
            html_text += "=" * 90 + "\n\n"
            
            for i, url in enumerate(briefing['all_urls'], 1):
                html_text += f"{i}. {url}\n"
            
            html_text += '</pre>'
            self.profile_display.setHtml(html_text)
            self.log_message(f"[PROFILER] Displaying profile for {person_name}")
        
        except Exception as e:
            self.log_message(f"[ERROR] Failed to display profile: {str(e)}")
            self.profile_display.setPlainText(f"Error loading profile: {str(e)}")
    
    def export_current_profile(self):
        """Export current person profile to file"""
        if not hasattr(self, 'current_profile'):
            self.log_message("[ERROR] No profile selected for export")
            QMessageBox.warning(self, "Warning", "Please select a person profile first!")
            return
        
        profile = self.current_profile
        person_name = profile['name'].replace(' ', '_')
        filename = f"profile_{person_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(os.path.dirname(__file__), 'reports', filename)
        
        self.log_message(f"[COMMAND] profile export --name=\"{profile['name']}\" --output={filename}")
        self.log_message(f"[INFO] Exporting profile for {profile['name']} to {filename}")
        
        try:
            # Create reports directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.profile_display.toPlainText())
            
            self.log_message(f"[SUCCESS] Profile exported to {filename}")
            QMessageBox.information(self, "Success", f"Profile exported to:\\n{filepath}")
        except Exception as e:
            self.log_message(f"[ERROR] Failed to export profile: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")
    
    def log_tor_message(self, message):
        """Log message to Tor logs display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color-coded message formatting
        formatted_message = f'<span style="color: #00ffff;">[{timestamp}]</span> '
        
        if "[ERROR]" in message:
            formatted_message += f'<span style="color: #ff0000;">[ERROR]</span> {message.replace("[ERROR]", "")}'
        elif "[WARN]" in message or "[NOTICE]" in message:
            formatted_message += f'<span style="color: #ff9933;">[WARN]</span> {message.replace("[WARN]", "").replace("[NOTICE]", "")}'
        elif "[TOR]" in message:
            formatted_message += f'<span style="color: #4EC9B0;">[TOR]</span> {message.replace("[TOR]", "")}'
        elif "[INFO]" in message:
            formatted_message += f'<span style="color: #007acc;">[INFO]</span> {message.replace("[INFO]", "")}'
        else:
            formatted_message += f'<span style="color: #d4d4d4;">{message}</span>'
        
        self.tor_log_display.append(formatted_message)
        self.tor_log_display.moveCursor(QTextCursor.End)
    
    def execute_console_command(self):
        """Execute command from console input"""
        command = self.command_input.text().strip()
        if not command:
            return
        
        # Clear input
        self.command_input.clear()
        
        # Log the command
        self.log_message(f"[CONSOLE] {command}")
        self.log_message("[INFO] Console commands are for display only in this version")
    
    def start_tor(self):
        """Start Tor process"""
        if self.tor_process and self.tor_process.state() == QProcess.Running:
            self.log_tor_message("[TOR] Tor is already running")
            return
        
        self.log_tor_message("[TOR] Starting Tor...")
        
        tor_path = os.path.join(os.path.dirname(__file__), 'tor', 'tor.exe')
        if not os.path.exists(tor_path):
            self.log_tor_message("[ERROR] Tor executable not found")
            QMessageBox.critical(self, "Error", "Tor executable not found at: " + tor_path)
            return
        
        self.tor_process = TorProcess(self)
        self.tor_process.log_signal.connect(self.log_tor_message)
        self.tor_process.start(tor_path, [])
        
        self.start_tor_button.setEnabled(False)
        self.stop_tor_button.setEnabled(True)
        self.tor_status_label.setText("Tor Status: STARTING...")
        self.tor_status_label.setStyleSheet("""
            QLabel {
                color: #ffff00;
                font-size: 13px;
                font-weight: normal;
                padding: 6px;
                font-family: 'Consolas', 'Courier New';
            }
        """)
        
        QTimer.singleShot(3000, self.check_tor_status)
    
    def stop_tor(self):
        """Stop Tor process"""
        if self.tor_process and self.tor_process.state() == QProcess.Running:
            self.log_tor_message("[TOR] Stopping Tor...")
            self.tor_process.terminate()
            if not self.tor_process.waitForFinished(3000):
                self.tor_process.kill()
            
            self.start_tor_button.setEnabled(True)
            self.stop_tor_button.setEnabled(False)
            self.tor_status_label.setText("Tor Status: STOPPED")
            self.tor_status_label.setStyleSheet("""
                QLabel {
                    color: #ff6c6c;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 6px;
                    font-family: 'Consolas', 'Courier New';
                }
            """)
        else:
            self.log_tor_message("[TOR] Tor is not running")
    
    def check_tor_status(self):
        """Check if Tor started successfully"""
        if self.tor_process and self.tor_process.state() == QProcess.Running:
            self.tor_status_label.setText("Tor Status: RUNNING")
            self.tor_status_label.setStyleSheet("""
                QLabel {
                    color: #4EC9B0;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 6px;
                    font-family: 'Consolas', 'Courier New';
                }
            """)
            self.log_tor_message("[TOR] Tor is running")
        else:
            self.tor_status_label.setText("Tor Status: FAILED")
            self.tor_status_label.setStyleSheet("""
                QLabel {
                    color: #ff6c6c;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 6px;
                    font-family: 'Consolas', 'Courier New';
                }
            """)
            self.start_tor_button.setEnabled(True)
            self.stop_tor_button.setEnabled(False)
            self.log_tor_message("[ERROR] Failed to start Tor")
    
    def clear_logs(self):
        """Clear logs"""
        self.log_display.clear()
        self.log_message("[SYSTEM] Logs cleared")
    
    def export_system_logs(self):
        """Export system logs to a text file"""
        self.log_message("[COMMAND] logs export --type=system")
        self.log_message("[INFO] Exporting system logs...")
        
        try:
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"system_logs_{timestamp}.txt"
            
            # Create logs directory if it doesn't exist
            logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            filepath = os.path.join(logs_dir, filename)
            
            # Get plain text from log display
            log_content = self.log_display.toPlainText()
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("PHOBOS SYSTEM LOGS EXPORT\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                f.write(log_content)
            
            self.log_message(f"[SUCCESS] System logs exported to: {filename}")
            QMessageBox.information(self, "Success", f"System logs exported to:\\n{filepath}")
            
        except Exception as e:
            error_msg = f"Failed to export logs: {str(e)}"
            self.log_message(f"[ERROR] {error_msg}")
            QMessageBox.critical(self, "Error", error_msg)
    
    def start_flask_server(self):
        """Start Flask web servers in background"""
        try:
            self.log_message("[INFO] Starting Flask threat reports server on port 7788...")
            
            # Start threat reports server
            self.flask_process = subprocess.Popen(
                [sys.executable, 'web/app.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(__file__)
            )
            
            self.log_message("[SUCCESS] Threat reports server started at http://127.0.0.1:7788")
            
            # Start search engine server
            self.log_message("[INFO] Starting Flask search engine on port 8080...")
            
            self.search_flask_process = subprocess.Popen(
                [sys.executable, 'web/search_app.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(__file__)
            )
            
            self.log_message("[SUCCESS] Search engine started at http://127.0.0.1:8080")
            
        except Exception as e:
            self.log_message(f"[ERROR] Failed to start Flask servers: {str(e)}")
    
    def closeEvent(self, event):
        """Handle window close event - stop all processes"""
        
        # Stop crawler
        if hasattr(self, 'go_crawler_process') and self.go_crawler_process:
            try:
                self.go_crawler_process.kill()
            except:
                pass
        
        # Kill all crawler processes
        try:
            import subprocess
            subprocess.run(['taskkill', '/F', '/IM', 'phobos-crawler.exe'], 
                         capture_output=True, timeout=5)
        except:
            pass
        
        # Stop Flask servers
        if hasattr(self, 'flask_process') and self.flask_process:
            try:
                self.flask_process.terminate()
                self.log_message("[INFO] Threat reports server stopped")
            except:
                pass
        
        if hasattr(self, 'search_flask_process') and self.search_flask_process:
            try:
                self.search_flask_process.terminate()
                self.log_message("[INFO] Search engine stopped")
            except:
                pass
        
        # Stop Tor
        if hasattr(self, 'tor_process') and self.tor_process:
            try:
                self.tor_process.kill()
            except:
                pass
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    app.setStyle('Fusion')
    
    gui = PHOBOSGui()
    gui.showMaximized()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
