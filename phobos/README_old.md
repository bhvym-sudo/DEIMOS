# PHOBOS GUI - Intelligence Gathering Platform

## Overview
Professional GUI interface for the PHOBOS web crawler with a forensics tool aesthetic inspired by Ghidra and x64dbg.

## Features

### Control Panel (Left Side)
- **Configuration Section**
  - Seed URL input field
  - Depth limit control (1-5 levels)
  - Download delay settings (0-10 seconds)
  - robots.txt compliance toggle

- **Crawler Control**
  - START CRAWLER button (green)
  - STOP CRAWLER button (red)
  - CLEAR LOGS button

- **Status Section**
  - Real-time status indicator
  - Progress bar
  - System state display

### Log Panel (Right Side)
- **System Logs Display**
  - Consolas monospace font for clarity
  - Timestamp for each log entry
  - Color-coded messages
  - Auto-scroll to latest entries
  - Black background with green text (terminal aesthetic)

## Installation

Install PyQt5:
```bash
pip install PyQt5
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

## Usage

### Launch GUI
```bash
python gui.py
```

### Configure Crawler
1. Enter target URL in "Seed URL" field
2. Set crawl depth (default: 2)
3. Configure download delay (default: 1 second)
4. Toggle robots.txt compliance

### Run Crawler
1. Click "START CRAWLER" button
2. Monitor logs in real-time
3. Wait for completion or click "STOP CRAWLER" to abort

### Clear Logs
Click "CLEAR LOGS" button to reset log display

## Design Features

### Color Scheme
- **Background**: Dark theme (#1a1a1a, #0a0a0a)
- **Primary Text**: Light gray (#CCCCCC)
- **Headers**: Green (#00FF00) - PHOBOS
- **Accents**: Orange (#FF6600), Cyan (#00CCFF)
- **Log Text**: Green on black (terminal style)

### Typography
- **Headers**: Courier New (32px bold)
- **Logs**: Consolas (11px monospace)
- **Labels**: Standard (12px)

### Layout
- **Header**: Full-width PHOBOS title with green border
- **Left Panel**: 400px control panel with grouped sections
- **Right Panel**: Expandable log display
- **Window Size**: 1400x800px

## Log Message Format
```
[HH:MM:SS] [LEVEL] Message
```

### Log Levels
- `[SYSTEM]` - System events
- `[INIT]` - Initialization
- `[OK]` - Success confirmations
- `[INFO]` - Information
- `[CONFIG]` - Configuration details
- `[START]` - Process started
- `[STOP]` - Process stopped
- `[COMPLETE]` - Task completed
- `[REPORT]` - Report generation
- `[STATS]` - Statistics
- `[SAVE]` - File operations
- `[ERROR]` - Errors
- `[TRACE]` - Stack traces

## Controls

### Keyboard Shortcuts
- Currently none (can be added)

### Mouse Operations
- Click buttons to execute actions
- Scroll logs with mouse wheel
- Select/copy text from logs

## Status States

### IDLE (Green)
- Crawler not running
- Ready to start new crawl

### RUNNING (Yellow)
- Crawler actively processing
- Stop button enabled

## Thread Management
- Crawler runs in separate QThread
- Non-blocking UI during crawl operations
- Signal-based log updates
- Clean thread termination on stop

## Technical Details

### Components
- `PHOBOSGui` - Main window class
- `CrawlerThread` - Background crawler thread
- Signal/Slot connections for thread-safe logging

### Thread Signals
- `log_signal` - Emit log messages to UI
- `finished_signal` - Notify completion

## Future Enhancements
- Real-time statistics dashboard
- Export logs to file
- Multiple crawler instances
- Tabbed interface for different operations
- Keyboard shortcuts
- Configuration presets
- Dark/Light theme toggle

## Notes
- GUI captures crawler stdout to prevent console spam
- Progress bar shows indeterminate state during active crawling
- All crawler operations run asynchronously
- Thread-safe logging implementation
