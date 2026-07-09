import sys
import json
import os
import re
import shutil
import urllib.request
import urllib.parse
import urllib.error
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog,
    QMessageBox, QStatusBar, QMenuBar, QMenu, QGridLayout,
    QGroupBox, QTabWidget, QListWidget, QSplitter,
    QAbstractItemView, QDialog,
    QDialogButtonBox, QHeaderView, QTableWidget,
    QTableWidgetItem, QProgressDialog, QSlider
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
    DATA_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).parent
    DATA_DIR = APP_DIR

LANGUAGES_DIR = DATA_DIR / "languages"
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "mp3tagger.log"

LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}

DEFAULT_SOURCES = {
    "musicbrainz": {
        "label": "MusicBrainz",
        "url": "https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json&limit=15",
        "headers": {"User-Agent": "GabMP3-IDTagger/1.0 (chris@example.com)"},
        "parser": "musicbrainz"
    },
    "discogs": {
        "label": "Discogs",
        "url": "https://api.discogs.com/database/search?q={query}&type=release&per_page=15",
        "headers": {"User-Agent": "GabMP3-IDTagger/1.0 +http://localhost", "Authorization": "Discogs key=YOUR_KEY, secret=YOUR_SECRET"},
        "parser": "discogs"
    },
    "spotify": {
        "label": "Spotify",
        "url": "https://api.spotify.com/v1/search?q={query}&type=track&limit=15",
        "headers": {"Authorization": "Bearer YOUR_TOKEN"},
        "parser": "spotify"
    },
    "lastfm": {
        "label": "Last.fm",
        "url": "https://ws.audioscrobbler.com/2.0/?method=track.search&track={query}&api_key=YOUR_API_KEY&format=json&limit=15",
        "headers": {},
        "parser": "lastfm"
    },
    "deezer": {
        "label": "Deezer",
        "url": "https://api.deezer.com/search?q={query}&limit=15",
        "headers": {},
        "parser": "deezer"
    },
    "itunes": {
        "label": "Apple iTunes",
        "url": "https://itunes.apple.com/search?term={query}&entity=song&limit=15",
        "headers": {},
        "parser": "itunes"
    },
    "audiodb": {
        "label": "TheAudioDB",
        "url": "https://www.theaudiodb.com/api/v1/json/2/searchtrack.php?s={query}",
        "headers": {},
        "parser": "audiodb"
    },
    "jamendo": {
        "label": "Jamendo",
        "url": "https://api.jamendo.com/v3.0/tracks/?search={query}&format=json&limit=15",
        "headers": {},
        "parser": "jamendo"
    },
    "soundcloud": {
        "label": "SoundCloud",
        "url": "https://api-v2.soundcloud.com/search/tracks?q={query}&limit=15",
        "headers": {"Authorization": "OAuth YOUR_TOKEN"},
        "parser": "soundcloud"
    }
}


class LogManager:
    _instance = None

    def __init__(self):
        self.level = "INFO"

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = LogManager()
        return cls._instance

    def set_level(self, level):
        if level in LOG_LEVELS:
            self.level = level

    def _log(self, level, message):
        if LOG_LEVELS.get(level, 99) >= LOG_LEVELS.get(self.level, 1):
            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] [{level}] {message}"
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def debug(self, message):
        self._log("DEBUG", message)

    def info(self, message):
        self._log("INFO", message)

    def warning(self, message):
        self._log("WARNING", message)

    def error(self, message):
        self._log("ERROR", message)


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "log_level" in cfg:
            LogManager.instance().set_level(cfg["log_level"])
        return cfg
    cfg = {"language": "de", "theme": "light", "log_level": "INFO"}
    cfg["sources"] = DEFAULT_SOURCES
    cfg["naming"] = {
        "folder": "{artist} - {album}",
        "file": "{track} - {artist} - {title}"
    }
    save_config(cfg)
    return cfg


def save_config(config):
    config["log_level"] = LogManager.instance().level
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_sources():
    cfg = load_config()
    s = cfg.get("sources", {})
    if not s:
        s = dict(DEFAULT_SOURCES)
    return s


def load_language(lang_code):
    lang_file = LANGUAGES_DIR / f"{lang_code}.json"
    if lang_file.exists():
        with open(lang_file, "r", encoding="utf-8") as f:
            return json.load(f)
    with open(LANGUAGES_DIR / "de.json", "r", encoding="utf-8") as f:
        return json.load(f)


class LanguageManager:
    _instance = None

    def __init__(self):
        self.config = load_config()
        self.current_lang = self.config.get("language", "de")
        self.strings = load_language(self.current_lang)

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = LanguageManager()
        return cls._instance

    def tr(self, key):
        return self.strings.get(key, key)

    def set_language(self, lang_code):
        self.current_lang = lang_code
        self.strings = load_language(lang_code)
        self.config["language"] = lang_code
        save_config(self.config)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        lm = LanguageManager.instance()
        self.setWindowTitle(lm.tr("about_title"))
        self.setFixedSize(400, 300)
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title = QLabel(lm.tr("app_title"))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a73e8;")
        layout.addWidget(title)

        version = QLabel("Version 0.0.1")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("font-size: 13px; color: #1a1a1a;")
        layout.addWidget(version)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #ddd;")
        layout.addWidget(separator)

        desc = QLabel(lm.tr("about_text"))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 12px; color: #1a1a1a; line-height: 1.5;")
        layout.addWidget(desc)

        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        btn_box.button(QDialogButtonBox.Ok).setText(lm.tr("ok"))
        layout.addWidget(btn_box)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
        """)


class SettingsDialog(QDialog):
    language_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumSize(560, 420)
        lm = LanguageManager.instance()
        log = LogManager.instance()
        self.sources = get_sources()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tabs = QTabWidget()

        lang_tab = QWidget()
        lang_layout = QVBoxLayout(lang_tab)
        lang_group = QGroupBox(lm.tr("settings_language"))
        group_lang = QVBoxLayout(lang_group)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(lm.tr("german"), "de")
        self.lang_combo.addItem(lm.tr("english"), "en")
        self.lang_combo.addItem(lm.tr("french"), "fr")
        self.lang_combo.addItem(lm.tr("spanish"), "es")
        idx = self.lang_combo.findData(lm.current_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        group_lang.addWidget(self.lang_combo)
        lang_layout.addWidget(lang_group)
        lang_layout.addStretch()
        tabs.addTab(lang_tab, lm.tr("language"))

        sources_tab = QWidget()
        sources_layout = QVBoxLayout(sources_tab)

        source_toolbar = QHBoxLayout()
        add_row_btn = QPushButton(lm.tr("add_source"))
        add_row_btn.clicked.connect(self.add_source_row)
        add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #34a853; color: white; border: none;
                padding: 6px 14px; font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #2d9249; }
        """)
        remove_btn = QPushButton(lm.tr("remove_selected"))
        remove_btn.clicked.connect(self.remove_source_row)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #ea4335; color: white; border: none;
                padding: 6px 14px; font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #d33426; }
        """)
        source_toolbar.addWidget(add_row_btn)
        source_toolbar.addWidget(remove_btn)
        source_toolbar.addStretch()
        sources_layout.addLayout(source_toolbar)

        self.source_table = QTableWidget()
        self.source_table.setColumnCount(5)
        self.source_table.setHorizontalHeaderLabels([
            lm.tr("source_key"), lm.tr("source_label"),
            lm.tr("source_url"), lm.tr("source_headers"),
            lm.tr("source_parser")
        ])
        self.source_table.horizontalHeader().setStretchLastSection(True)
        self.source_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.source_table.setAlternatingRowColors(True)
        self.source_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #b0b0b0; border-radius: 4px;
                font-size: 12px; color: #0d0d0d; background: #ffffff;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item { padding: 4px 6px; }
            QHeaderView::section {
                background-color: #f0f0f0; color: #1a1a1a;
                font-weight: bold; padding: 6px; border: 1px solid #d0d0d0;
            }
        """)
        self.populate_source_table()
        sources_layout.addWidget(self.source_table, 1)

        sources_info = QLabel(lm.tr("sources_info"))
        sources_info.setWordWrap(True)
        sources_info.setStyleSheet("color: #555; font-size: 11px;")
        sources_layout.addWidget(sources_info)

        tabs.addTab(sources_tab, lm.tr("tag_sources"))

        admin_tab = QWidget()
        admin_layout = QVBoxLayout(admin_tab)
        log_group = QGroupBox(lm.tr("log_level"))
        group_log = QVBoxLayout(log_group)
        self.log_combo = QComboBox()
        current_log = log.level
        for lvl in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            self.log_combo.addItem(lvl, lvl)
        idx = self.log_combo.findData(current_log)
        if idx >= 0:
            self.log_combo.setCurrentIndex(idx)
        group_log.addWidget(self.log_combo)
        info_label = QLabel(lm.tr("log_level_info"))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #1a1a1a; font-size: 11px; padding: 4px 0;")
        group_log.addWidget(info_label)
        admin_layout.addWidget(log_group)

        naming_group = QGroupBox("Naming")
        naming_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #c0c0c0;
                border-radius: 4px; margin-top: 8px; padding-top: 10px; background: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        naming_inner = QVBoxLayout(naming_group)
        naming_inner.setSpacing(6)

        fn_row = QHBoxLayout()
        fn_label = QLabel("Folder format:")
        fn_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #1a1a1a;")
        self.cfg_folder_combo = QComboBox()
        self.cfg_folder_combo.addItems([
            "{artist} - {album}", "{artist}/{album}", "{album}",
            "{artist} - {year} - {album}", "{genre}/{artist} - {album}"
        ])
        cfg_naming = load_config().get("naming", {})
        folder_idx = self.cfg_folder_combo.findText(cfg_naming.get("folder", "{artist} - {album}"))
        if folder_idx >= 0:
            self.cfg_folder_combo.setCurrentIndex(folder_idx)
        fn_row.addWidget(fn_label)
        fn_row.addWidget(self.cfg_folder_combo, 1)
        naming_inner.addLayout(fn_row)

        fl_row = QHBoxLayout()
        fl_label = QLabel("File format:")
        fl_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #1a1a1a;")
        self.cfg_file_combo = QComboBox()
        self.cfg_file_combo.addItems([
            "{track} - {artist} - {title}", "{artist} - {title}",
            "{track} {title}", "{artist} - {year} - {title}", "{title}"
        ])
        file_idx = self.cfg_file_combo.findText(cfg_naming.get("file", "{track} - {artist} - {title}"))
        if file_idx >= 0:
            self.cfg_file_combo.setCurrentIndex(file_idx)
        fl_row.addWidget(fl_label)
        fl_row.addWidget(self.cfg_file_combo, 1)
        naming_inner.addLayout(fl_row)

        admin_layout.addWidget(naming_group)
        admin_layout.addStretch()
        tabs.addTab(admin_tab, lm.tr("admin"))

        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton(lm.tr("save_settings"))
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        cancel_btn = QPushButton(lm.tr("cancel"))
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #1a1a1a;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
                color: #0d0d0d;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #b0b0b0;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: #0d0d0d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #0d0d0d;
            }
            QComboBox {
                padding: 6px;
                border: 1px solid #b0b0b0;
                border-radius: 4px;
                background: white;
                color: #0d0d0d;
            }
            QComboBox:focus {
                border-color: #1a73e8;
            }
            QComboBox QAbstractItemView {
                color: #0d0d0d;
                background: white;
                selection-background-color: #e8f0fe;
                selection-color: #1a73e8;
            }
            QTabWidget::pane {
                border: 1px solid #b0b0b0;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                padding: 8px 16px;
                background-color: #e8e8e8;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #333333;
                border: 1px solid #b0b0b0;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1a73e8;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #dcdcdc;
            }
            QLabel {
                color: #0d0d0d;
            }
        """)

    def populate_source_table(self):
        self.source_table.setRowCount(0)
        for key, src in self.sources.items():
            row = self.source_table.rowCount()
            self.source_table.insertRow(row)
            self.source_table.setItem(row, 0, QTableWidgetItem(key))
            self.source_table.setItem(row, 1, QTableWidgetItem(src.get("label", "")))
            self.source_table.setItem(row, 2, QTableWidgetItem(src.get("url", "")))
            headers_str = json.dumps(src.get("headers", {}), ensure_ascii=False)
            self.source_table.setItem(row, 3, QTableWidgetItem(headers_str))
            self.source_table.setItem(row, 4, QTableWidgetItem(src.get("parser", "musicbrainz")))

    def add_source_row(self):
        row = self.source_table.rowCount()
        self.source_table.insertRow(row)
        self.source_table.setItem(row, 0, QTableWidgetItem("new_source"))
        self.source_table.setItem(row, 1, QTableWidgetItem("New Source"))
        self.source_table.setItem(row, 2, QTableWidgetItem("https://example.com/api?query={query}&fmt=json"))
        self.source_table.setItem(row, 3, QTableWidgetItem('{"User-Agent": "GabMP3-IDTagger/1.0"}'))
        self.source_table.setItem(row, 4, QTableWidgetItem("musicbrainz"))

    def remove_source_row(self):
        rows = set(i.row() for i in self.source_table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self.source_table.removeRow(row)

    def table_to_sources(self):
        sources = {}
        for row in range(self.source_table.rowCount()):
            key_item = self.source_table.item(row, 0)
            if key_item is None or not key_item.text().strip():
                continue
            key = key_item.text().strip()
            label = self.source_table.item(row, 1).text().strip() if self.source_table.item(row, 1) else ""
            url = self.source_table.item(row, 2).text().strip() if self.source_table.item(row, 2) else ""
            headers_str = self.source_table.item(row, 3).text().strip() if self.source_table.item(row, 3) else "{}"
            parser = self.source_table.item(row, 4).text().strip() if self.source_table.item(row, 4) else "musicbrainz"
            try:
                headers = json.loads(headers_str) if headers_str else {}
            except json.JSONDecodeError:
                headers = {"User-Agent": "GabMP3-IDTagger/1.0"}
            if url:
                sources[key] = {
                    "label": label or key,
                    "url": url,
                    "headers": headers,
                    "parser": parser
                }
        return sources

    def save_settings(self):
        lm = LanguageManager.instance()
        log = LogManager.instance()
        new_lang = self.lang_combo.currentData()
        new_log = self.log_combo.currentData()

        new_sources = self.table_to_sources()
        if not new_sources:
            QMessageBox.warning(self, lm.tr("error_invalid_file"), "At least one valid source row is required (key + url).")
            return
        cfg = load_config()
        cfg["sources"] = new_sources
        cfg["naming"] = {
            "folder": self.cfg_folder_combo.currentText(),
            "file": self.cfg_file_combo.currentText()
        }
        save_config(cfg)
        self.sources = new_sources

        log.set_level(new_log)
        lm.set_language(new_lang)
        log.info(f"Einstellungen gespeichert: Sprache={new_lang}, Log-Level={new_log}")
        self.language_changed.emit()
        self.accept()


class SearchOnlineDialog(QDialog):
    def __init__(self, parent=None, preselected_source=None):
        super().__init__(parent)
        self.setWindowTitle("Online-Suche")
        self.setMinimumSize(650, 450)
        self.lm = LanguageManager.instance()
        self.selected_tags = None
        self.sources = get_sources()
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        source_layout = QHBoxLayout()
        self.source_label = QLabel()
        self.source_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.source_combo = QComboBox()
        self.source_combo.setStyleSheet("padding: 4px; border: 1px solid #b0b0b0; border-radius: 4px;")
        for key, src in self.sources.items():
            self.source_combo.addItem(src.get("label", key), key)
        if preselected_source:
            idx = self.source_combo.findData(preselected_source)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        source_layout.addWidget(self.source_label)
        source_layout.addWidget(self.source_combo, 1)
        layout.addLayout(source_layout)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Interpret - Titel")
        self.search_input.returnPressed.connect(self.do_search)
        self.search_input.setStyleSheet("padding: 8px; font-size: 14px;")
        self.search_btn = QPushButton()
        self.search_btn.clicked.connect(self.do_search)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                padding: 8px 20px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.source_info = QLabel()
        self.source_info.setStyleSheet("color: #555; font-size: 11px; padding-bottom: 2px;")
        layout.addWidget(self.source_info)

        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e8f0fe;
                color: #1a73e8;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.results_list, 1)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #1a1a1a; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton()
        self.apply_btn.clicked.connect(self.apply_selection)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #34a853;
                color: white;
                border: none;
                padding: 8px 24px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2d9249; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #1a1a1a;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
            }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.results_list.itemClicked.connect(self.on_result_clicked)
        self.apply_language()

    def apply_language(self):
        self.setWindowTitle(self.lm.tr("search"))
        self.source_label.setText(self.lm.tr("source"))
        self.source_info.setText(self.lm.tr("source_info"))
        self.search_btn.setText(self.lm.tr("search"))
        self.search_input.setPlaceholderText(f"{self.lm.tr('artist')} - {self.lm.tr('title')}")
        self.apply_btn.setText(self.lm.tr("apply"))
        self.cancel_btn.setText(self.lm.tr("cancel"))
        self.status_label.setText("")
        # Adjust controls to fit translated text
        self.search_btn.adjustSize()
        self.apply_btn.adjustSize()
        self.cancel_btn.adjustSize()
        self.source_label.adjustSize()
        self.source_info.adjustSize()
        self.setMinimumSize(self.minimumSizeHint())

    def do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        self.results_list.clear()
        self.apply_btn.setEnabled(False)
        self.selected_tags = None
        self.status_label.setText(self.lm.tr("status_processing"))
        self.search_btn.setEnabled(False)

        thread = threading.Thread(target=self._search_thread, args=(query,), daemon=True)
        thread.start()

    def _search_thread(self, query):
        try:
            source_key = self.source_combo.currentData()
            src = self.sources.get(source_key, list(self.sources.values())[0])
            url_template = src["url"]
            q = urllib.parse.quote(query)
            url = url_template.replace("{query}", q)
            headers = src.get("headers", {"User-Agent": "GabMP3-IDTagger/1.0"})
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())

            parser = src.get("parser", "musicbrainz")
            items = []

            if parser == "musicbrainz":
                for rec in data.get("recordings", []):
                    artist = "?"
                    if rec.get("artist-credit"):
                        artist = "".join(
                            c.get("name", "") + (c.get("joinphrase", "") or "")
                            for c in rec["artist-credit"]
                        )
                    album = "?"
                    year = ""
                    if rec.get("releases"):
                        album = rec["releases"][0].get("title", "?")
                        year = rec["releases"][0].get("date", "")[:4]
                    items.append({
                        "title": rec.get("title", "?"),
                        "artist": artist,
                        "album": album,
                        "year": year,
                        "id": rec.get("id", "")
                    })

            elif parser == "discogs":
                for r in data.get("results", []):
                    artist = "?"
                    if r.get("artist"):
                        artist = r["artist"] if isinstance(r["artist"], str) else ", ".join(r["artist"])
                    title = r.get("title", "?")
                    album = r.get("title", "?")
                    year = r.get("year", "")
                    items.append({"title": title, "artist": artist, "album": album, "year": str(year) if year else "", "id": str(r.get("id", ""))})

            elif parser == "spotify":
                for t in data.get("tracks", {}).get("items", []):
                    artist = ", ".join(a.get("name", "?") for a in t.get("artists", []))
                    album = t.get("album", {}).get("name", "?")
                    year = t.get("album", {}).get("release_date", "")[:4]
                    items.append({"title": t.get("name", "?"), "artist": artist, "album": album, "year": year, "id": t.get("id", "")})

            elif parser == "lastfm":
                for t in data.get("results", {}).get("trackmatches", {}).get("track", []):
                    items.append({"title": t.get("name", "?"), "artist": t.get("artist", "?"), "album": "", "year": "", "id": t.get("mbid", "")})

            elif parser == "deezer":
                for t in data.get("data", []):
                    artist = t.get("artist", {}).get("name", "?")
                    album = t.get("album", {}).get("title", "?")
                    items.append({"title": t.get("title", "?"), "artist": artist, "album": album, "year": "", "id": str(t.get("id", ""))})

            elif parser == "itunes":
                for r in data.get("results", []):
                    if r.get("wrapperType") == "track":
                        items.append({"title": r.get("trackName", "?"), "artist": r.get("artistName", "?"), "album": r.get("collectionName", "?"), "year": (r.get("releaseDate", "")[:4]) if r.get("releaseDate") else "", "id": str(r.get("trackId", ""))})

            elif parser == "audiodb":
                for t in data.get("track", []):
                    items.append({"title": t.get("strTrack", "?"), "artist": t.get("strArtist", "?"), "album": t.get("strAlbum", "?"), "year": t.get("intYear", ""), "id": t.get("idTrack", "")})

            elif parser == "jamendo":
                for t in data.get("results", []):
                    artist = t.get("artist_name", "?")
                    album = t.get("album_name", "?")
                    items.append({"title": t.get("name", "?"), "artist": artist, "album": album, "year": "", "id": t.get("id", "")})

            elif parser == "soundcloud":
                for t in data.get("collection", []):
                    u = t.get("user", {})
                    items.append({"title": t.get("title", "?"), "artist": u.get("username", "?"), "album": "", "year": "", "id": str(t.get("id", ""))})

            else:
                recs = data if isinstance(data, list) else [data]
                for r in recs:
                    items.append({"title": r.get("title", "?"), "artist": r.get("artist", "?"), "album": r.get("album", "?"), "year": str(r.get("year", "") or ""), "id": str(r.get("id", "") or "")})

            from PySide6.QtCore import QMetaObject, Qt as QtCore, Q_ARG
            QMetaObject.invokeMethod(
                self.results_list, "clear", QtCore.QueuedConnection
            )
            for item in items:
                display = f"{item['artist']} - {item['title']}"
                if item['album'] != "?":
                    display += f"  |  {item['album']}"
                if item['year']:
                    display += f" ({item['year']})"
                QMetaObject.invokeMethod(
                    self.results_list, "addItem",
                    QtCore.QueuedConnection,
                    Q_ARG(str, display)
                )
                idx = self.results_list.count() - 1
                self.results_list.item(idx).setData(Qt.UserRole, item)

            status_text = f"{len(items)} Ergebnisse" if items else self.lm.tr("no_results")
            QMetaObject.invokeMethod(
                self.status_label, "setText",
                QtCore.QueuedConnection,
                Q_ARG(str, status_text)
            )
        except Exception as e:
            error_text = f"{self.lm.tr('status_error')}: {str(e)}"
            QMetaObject.invokeMethod(
                self.status_label, "setText",
                QtCore.QueuedConnection,
                Q_ARG(str, error_text)
            )
        finally:
            QMetaObject.invokeMethod(
                self.search_btn, "setEnabled",
                QtCore.QueuedConnection,
                Q_ARG(bool, True)
            )

    def on_result_clicked(self, item):
        self.selected_tags = item.data(Qt.UserRole)
        self.apply_btn.setEnabled(True)

    def apply_selection(self):
        if self.selected_tags:
            self.accept()


class ToastWidget(QLabel):
    def __init__(self, text, parent, duration=3000):
        super().__init__(parent)
        self.setStyleSheet("""
            background-color: #323232;
            color: #ffffff;
            font-size: 13px;
            font-weight: bold;
            padding: 12px 24px;
            border-radius: 8px;
        """)
        self.setText(text)
        self.adjustSize()
        self.move(int((parent.width() - self.width()) / 2), parent.height() - self.height() - 60)
        self.show()

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

        QTimer.singleShot(duration, self.fade_out)

    def fade_out(self):
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.InCubic)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.lm = LanguageManager.instance()
        self.init_ui()
        self.apply_language()
        self.apply_modern_style()
        LogManager.instance().info("Programm gestartet")

        # Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player_playlist = []
        self.player_current_index = -1

    def apply_modern_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6f8;
            }
            QMenuBar {
                background-color: #ffffff;
                border-bottom: 2px solid #d0d0d0;
                padding: 3px;
                font-size: 13px;
                color: #0d0d0d;
            }
            QMenuBar::item {
                padding: 6px 14px;
                background: transparent;
                border-radius: 4px;
                color: #0d0d0d;
                font-weight: 500;
            }
            QMenuBar::item:selected {
                background-color: #dce8fa;
                color: #0d47a1;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                padding: 4px;
                color: #0d0d0d;
            }
            QMenu::item {
                padding: 8px 30px 8px 20px;
                border-radius: 4px;
                color: #0d0d0d;
            }
            QMenu::item:selected {
                background-color: #dce8fa;
                color: #0d47a1;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #c0c0c0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
                background-color: #ffffff;
                color: #0d0d0d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #0d0d0d;
            }
            QLineEdit {
                padding: 8px 10px;
                border: 2px solid #b0b0b0;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 13px;
                color: #000000;
                font-weight: 500;
            }
            QLineEdit:focus {
                border-color: #0d47a1;
                background-color: #ffffff;
                color: #000000;
            }
            QLineEdit:disabled {
                background-color: #e8e8e8;
                color: #555555;
            }
            QPushButton {
                padding: 8px 16px;
                border: 2px solid #c0c0c0;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                color: #0d0d0d;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border-color: #a0a0a0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QStatusBar {
                background-color: #ffffff;
                border-top: 2px solid #d0d0d0;
                font-size: 12px;
                color: #0d0d0d;
                font-weight: 500;
            }
            QListWidget {
                border: 2px solid #c0c0c0;
                border-radius: 6px;
                background-color: #ffffff;
                padding: 4px;
                font-size: 13px;
                color: #0d0d0d;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
                color: #0d0d0d;
            }
            QListWidget::item:selected {
                background-color: #dce8fa;
                color: #0d47a1;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 2px solid #c0c0c0;
                border-top: none;
                border-radius: 0px 0px 6px 6px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                padding: 8px 22px;
                margin-right: 2px;
                background-color: #e8e8e8;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                color: #333333;
                font-weight: 500;
                border: 1px solid #c0c0c0;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0d47a1;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #dcdcdc;
            }
            QComboBox {
                padding: 6px 8px;
                border: 2px solid #b0b0b0;
                border-radius: 4px;
                background: white;
                color: #0d0d0d;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:focus {
                border-color: #0d47a1;
            }
            QComboBox QAbstractItemView {
                color: #0d0d0d;
                background: white;
                font-size: 12px;
                selection-background-color: #dce8fa;
                selection-color: #0d47a1;
            }
            QSplitter::handle {
                background: #c0c0c0;
                width: 3px;
            }
            QStatusBar::item {
                border: none;
            }
        """)

    def init_ui(self):
        self.setWindowTitle("Gab MP3-IDTagger")
        self.setMinimumSize(1100, 750)
        self.setGeometry(100, 100, 1100, 750)

        self.create_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_label = QLabel()
        self.file_list_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #000000;")
        left_layout.addWidget(self.file_list_label)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_list.itemClicked.connect(self.on_file_selected)
        left_layout.addWidget(self.file_list)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.main_tabs = QTabWidget()

        # --- Tab 1: Tag Editor ---
        tag_tab = QWidget()
        tag_tab_layout = QVBoxLayout(tag_tab)
        tag_tab_layout.setContentsMargins(4, 4, 4, 4)

        self.tag_group = QGroupBox()
        tag_grid = QGridLayout()
        tag_grid.setSpacing(8)

        source_header_w = QWidget()
        source_header_layout = QHBoxLayout(source_header_w)
        source_header_layout.setContentsMargins(0, 0, 0, 0)
        source_header_layout.setSpacing(6)

        self.search_online_btn = QPushButton()
        self.search_online_btn.clicked.connect(self.search_online)
        self.search_online_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6d00; color: white; border: none;
                padding: 8px 16px; font-weight: bold; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #e65100; }
        """)
        source_header_layout.addWidget(self.search_online_btn)

        self.source_combo_label = QLabel()
        self.source_combo_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #1a1a1a;")
        self.source_combo = QComboBox()
        self.source_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px; border: 1px solid #b0b0b0;
                border-radius: 4px; font-size: 12px; background: white;
            }
        """)
        self.refresh_source_combo()
        source_header_layout.addWidget(self.source_combo_label)
        source_header_layout.addWidget(self.source_combo, 1)

        tag_grid.addWidget(source_header_w, 0, 0, 1, 2)
        tag_grid.setRowMinimumHeight(0, 36)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.title_input = QLineEdit()
        tag_grid.addWidget(self.title_label, 1, 0)
        tag_grid.addWidget(self.title_input, 1, 1)

        self.artist_label = QLabel()
        self.artist_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.artist_input = QLineEdit()
        tag_grid.addWidget(self.artist_label, 2, 0)
        tag_grid.addWidget(self.artist_input, 2, 1)

        self.album_label = QLabel()
        self.album_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.album_input = QLineEdit()
        tag_grid.addWidget(self.album_label, 3, 0)
        tag_grid.addWidget(self.album_input, 3, 1)

        self.year_label = QLabel()
        self.year_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.year_input = QLineEdit()
        tag_grid.addWidget(self.year_label, 4, 0)
        tag_grid.addWidget(self.year_input, 4, 1)

        self.genre_label = QLabel()
        self.genre_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.genre_input = QLineEdit()
        tag_grid.addWidget(self.genre_label, 5, 0)
        tag_grid.addWidget(self.genre_input, 5, 1)

        self.track_label = QLabel()
        self.track_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.track_input = QLineEdit()
        tag_grid.addWidget(self.track_label, 6, 0)
        tag_grid.addWidget(self.track_input, 6, 1)

        self.comment_label = QLabel()
        self.comment_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.comment_input = QLineEdit()
        tag_grid.addWidget(self.comment_label, 7, 0)
        tag_grid.addWidget(self.comment_input, 7, 1)

        self.composer_label = QLabel()
        self.composer_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.composer_input = QLineEdit()
        tag_grid.addWidget(self.composer_label, 8, 0)
        tag_grid.addWidget(self.composer_input, 8, 1)

        self.album_artist_label = QLabel()
        self.album_artist_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.album_artist_input = QLineEdit()
        tag_grid.addWidget(self.album_artist_label, 9, 0)
        tag_grid.addWidget(self.album_artist_input, 9, 1)

        self.tag_group.setLayout(tag_grid)
        tag_tab_layout.addWidget(self.tag_group)

        tag_btn_layout = QHBoxLayout()
        tag_btn_layout.setSpacing(10)

        self.read_btn = QPushButton()
        self.read_btn.clicked.connect(self.read_tags)
        self.read_btn.setStyleSheet("""
            QPushButton { background-color: #1a73e8; color: white; border: none;
                padding: 10px 24px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #1557b0; }
        """)

        self.write_btn = QPushButton()
        self.write_btn.clicked.connect(self.write_tags)
        self.write_btn.setStyleSheet("""
            QPushButton { background-color: #34a853; color: white; border: none;
                padding: 10px 24px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #2d9249; }
        """)

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear_tags)
        self.clear_btn.setStyleSheet("""
            QPushButton { background-color: #ea4335; color: white; border: none;
                padding: 10px 24px; font-weight: bold; border-radius: 6px; }
            QPushButton:hover { background-color: #d33426; }
        """)

        tag_btn_layout.addWidget(self.read_btn)
        tag_btn_layout.addWidget(self.write_btn)
        tag_btn_layout.addWidget(self.clear_btn)
        tag_btn_layout.addStretch()
        tag_tab_layout.addLayout(tag_btn_layout)
        self.main_tabs.addTab(tag_tab, "Tagging")

        # --- Tab 2: Folder Tasks ---
        folder_tab = QWidget()
        folder_layout = QVBoxLayout(folder_tab)
        folder_layout.setContentsMargins(4, 4, 4, 4)
        folder_layout.setSpacing(10)

        dest_layout = QHBoxLayout()
        dest_layout.setSpacing(6)
        self.dest_path_label = QLabel("Destination:")
        self.dest_path_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.dest_path_input = QLineEdit()
        self.dest_path_input.setPlaceholderText("Zielordner auswählen oder Pfad eingeben...")
        self.dest_browse_btn = QPushButton("...")
        self.dest_browse_btn.setFixedWidth(36)
        self.dest_browse_btn.clicked.connect(self.choose_dest_folder)
        self.dest_browse_btn.setStyleSheet("""
            QPushButton { background-color: #5f6368; color: white; border: none;
                padding: 8px 10px; font-weight: bold; border-radius: 4px; font-size: 14px; }
            QPushButton:hover { background-color: #4d5156; }
        """)
        dest_layout.addWidget(self.dest_path_label)
        dest_layout.addWidget(self.dest_path_input, 1)
        dest_layout.addWidget(self.dest_browse_btn)
        folder_layout.addLayout(dest_layout)

        self.move_files_btn = QPushButton()
        self.move_files_btn.clicked.connect(self.move_files_to_dest)
        self.move_files_btn.setStyleSheet("""
            QPushButton { background-color: #e67e22; color: white; border: none;
                padding: 14px 32px; font-weight: bold; border-radius: 6px; font-size: 14px; }
            QPushButton:hover { background-color: #d35400; }
        """)
        folder_layout.addWidget(self.move_files_btn)
        folder_layout.addStretch()

        self.main_tabs.addTab(folder_tab, "Folder Tasks")

        # --- Tab 3: Player ---
        player_tab = QWidget()
        player_layout = QVBoxLayout(player_tab)
        player_layout.setContentsMargins(4, 4, 4, 4)
        player_layout.setSpacing(8)

        # Playlist
        playlist_row = QHBoxLayout()
        self.playlist_label = QLabel("Playlist:")
        self.playlist_label.setStyleSheet("font-weight: 700; color: #000000; font-size: 13px;")
        self.playlist_list = QListWidget()
        self.playlist_list.setAlternatingRowColors(True)
        self.playlist_list.setStyleSheet("""
            QListWidget { border: 1px solid #b0b0b0; border-radius: 4px;
                background: #ffffff; color: #0d0d0d; font-size: 12px; }
            QListWidget::item:selected { background-color: #dce8fa; color: #0d47a1; font-weight: bold; }
        """)
        self.playlist_list.itemDoubleClicked.connect(self.play_selected)
        player_layout.addWidget(self.playlist_label)
        player_layout.addWidget(self.playlist_list, 1)

        playlist_btn_row = QHBoxLayout()
        playlist_btn_row.setSpacing(6)
        self.add_to_playlist_btn = QPushButton("+ Add")
        self.add_to_playlist_btn.clicked.connect(self.add_files_to_playlist)
        self.add_to_playlist_btn.setStyleSheet("""QPushButton { background: #1a73e8; color: white; border: none;
            padding: 6px 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background: #1557b0; }""")
        self.remove_from_playlist_btn = QPushButton("- Remove")
        self.remove_from_playlist_btn.clicked.connect(self.remove_from_playlist)
        self.remove_from_playlist_btn.setStyleSheet("""QPushButton { background: #ea4335; color: white; border: none;
            padding: 6px 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background: #d33426; }""")
        self.clear_playlist_btn = QPushButton("Clear")
        self.clear_playlist_btn.clicked.connect(self.clear_playlist)
        self.clear_playlist_btn.setStyleSheet("""QPushButton { background: #5f6368; color: white; border: none;
            padding: 6px 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background: #4d5156; }""")
        self.save_playlist_btn = QPushButton("Save M3U")
        self.save_playlist_btn.clicked.connect(self.save_playlist)
        self.save_playlist_btn.setStyleSheet("""QPushButton { background: #34a853; color: white; border: none;
            padding: 6px 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background: #2d9249; }""")
        playlist_btn_row.addWidget(self.add_to_playlist_btn)
        playlist_btn_row.addWidget(self.remove_from_playlist_btn)
        playlist_btn_row.addWidget(self.clear_playlist_btn)
        playlist_btn_row.addWidget(self.save_playlist_btn)
        playlist_btn_row.addStretch()
        player_layout.addLayout(playlist_btn_row)

        # Now playing
        self.now_playing_label = QLabel("No file selected")
        self.now_playing_label.setStyleSheet("font-weight: 700; color: #0d47a1; font-size: 13px; padding: 4px 0;")
        player_layout.addWidget(self.now_playing_label)

        # Seek slider + time
        seek_row = QHBoxLayout()
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 100)
        self.seek_slider.sliderMoved.connect(self.seek_position)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #d0d0d0; border-radius: 3px; }
            QSlider::handle:horizontal { background: #1a73e8; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #1a73e8; border-radius: 3px; }
        """)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 11px; color: #333;")
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.time_label)
        player_layout.addLayout(seek_row)

        # Transport controls
        transport_row = QHBoxLayout()
        transport_row.setSpacing(8)
        self.prev_btn = QPushButton("|<")
        self.prev_btn.clicked.connect(self.play_prev)
        self.prev_btn.setStyleSheet("""QPushButton { background: #5f6368; color: white; border: none;
            padding: 10px 20px; font-weight: bold; border-radius: 6px; font-size: 14px; }
            QPushButton:hover { background: #4d5156; }""")
        self.play_btn = QPushButton(">")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setStyleSheet("""QPushButton { background-color: #1a73e8; color: white; border: none;
            padding: 10px 28px; font-weight: bold; border-radius: 6px; font-size: 16px; }
            QPushButton:hover { background-color: #1557b0; }""")
        self.stop_btn = QPushButton("[]")
        self.stop_btn.clicked.connect(self.stop_player)
        self.stop_btn.setStyleSheet("""QPushButton { background-color: #ea4335; color: white; border: none;
            padding: 10px 20px; font-weight: bold; border-radius: 6px; font-size: 14px; }
            QPushButton:hover { background-color: #d33426; }""")
        self.next_btn = QPushButton(">|")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setStyleSheet("""QPushButton { background-color: #5f6368; color: white; border: none;
            padding: 10px 20px; font-weight: bold; border-radius: 6px; font-size: 14px; }
            QPushButton:hover { background-color: #4d5156; }""")
        transport_row.addWidget(self.prev_btn)
        transport_row.addWidget(self.play_btn)
        transport_row.addWidget(self.stop_btn)
        transport_row.addWidget(self.next_btn)

        # Volume
        transport_row.addSpacing(20)
        vol_label = QLabel("Volume:")
        vol_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #1a1a1a;")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.vol_slider.setFixedWidth(120)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #d0d0d0; border-radius: 3px; }
            QSlider::handle:horizontal { background: #34a853; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #34a853; border-radius: 3px; }
        """)
        transport_row.addWidget(vol_label)
        transport_row.addWidget(self.vol_slider)
        transport_row.addStretch()
        player_layout.addLayout(transport_row)

        self.main_tabs.addTab(player_tab, "Player")

        right_layout.addWidget(self.main_tabs, 1)

        self.exit_btn = QPushButton()
        self.exit_btn.clicked.connect(self.close)
        self.exit_btn.setStyleSheet("""
            QPushButton { background-color: #5f6368; color: white; border: none;
                padding: 12px 24px; font-weight: bold; border-radius: 6px; font-size: 13px; }
            QPushButton:hover { background-color: #4d5156; }
        """)
        right_layout.addWidget(self.exit_btn)

        splitter.addWidget(right_panel)

        splitter.setSizes([250, 750])
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label, 1)

    def create_menu_bar(self):
        menubar = self.menuBar()

        self.file_menu = menubar.addMenu("")
        self.open_file_action = QAction("", self)
        self.open_file_action.triggered.connect(self.open_file_dialog)
        self.file_menu.addAction(self.open_file_action)

        self.open_folder_action = QAction("", self)
        self.open_folder_action.triggered.connect(self.open_folder_dialog)
        self.file_menu.addAction(self.open_folder_action)

        self.file_menu.addSeparator()

        self.exit_action = QAction("", self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

        self.settings_menu = menubar.addMenu("")
        self.settings_action = QAction("", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.settings_menu.addAction(self.settings_action)

        self.help_menu = menubar.addMenu("")
        self.about_action = QAction("", self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)

    def apply_language(self):
        lm = self.lm
        self.setWindowTitle(lm.tr("window_title"))

        self.file_menu.setTitle(lm.tr("file"))
        self.open_file_action.setText(lm.tr("open_file"))
        self.open_folder_action.setText(lm.tr("open_folder"))
        self.exit_action.setText(lm.tr("exit"))

        self.settings_menu.setTitle(lm.tr("settings"))
        self.settings_action.setText(lm.tr("settings"))

        self.help_menu.setTitle(lm.tr("help"))
        self.about_action.setText(lm.tr("about"))

        self.main_tabs.setTabText(0, "Tagging")
        self.main_tabs.setTabText(1, "Folder Tasks")
        self.main_tabs.setTabText(2, "Player")
        self.playlist_label.setText("Playlist:")

        self.tag_group.setTitle(lm.tr("tags"))
        self.title_label.setText(lm.tr("title"))
        self.artist_label.setText(lm.tr("artist"))
        self.album_label.setText(lm.tr("album"))
        self.year_label.setText(lm.tr("year"))
        self.genre_label.setText(lm.tr("genre"))
        self.track_label.setText(lm.tr("track"))
        self.comment_label.setText(lm.tr("comment"))
        self.composer_label.setText(lm.tr("composer"))
        self.album_artist_label.setText(lm.tr("album_artist"))

        self.search_online_btn.setText(lm.tr("search_online"))
        self.source_combo_label.setText(lm.tr("source") + ":")
        self.read_btn.setText(lm.tr("read_tags"))
        self.write_btn.setText(lm.tr("write_tags"))
        self.clear_btn.setText(lm.tr("clear_tags"))

        self.dest_path_label.setText(lm.tr("destination") if lm.tr("destination") != "destination" else "Destination:")
        self.dest_path_input.setPlaceholderText(lm.tr("select_folder") + "...")
        self.move_files_btn.setText(lm.tr("move_selected") if lm.tr("move_selected") != "move_selected" else "Move to Destination")

        self.exit_btn.setText(lm.tr("exit"))

        self.file_list_label.setText(lm.tr("select_file"))

        self.status_label.setText(lm.tr("status_ready"))

        # Resize controls to fit translated text
        self.main_tabs.setMinimumWidth(self.main_tabs.sizeHint().width())
        self.main_tabs.adjustSize()
        self.tag_group.adjustSize()
        self.search_online_btn.adjustSize()
        for btn in [self.read_btn, self.write_btn, self.clear_btn,
                     self.move_files_btn, self.exit_btn]:
            btn.adjustSize()
        self.file_list_label.adjustSize()
        self.source_combo_label.adjustSize()
        self.status_bar.adjustSize()
        # Re-apply the window's minimum size to catch any growth
        self.setMinimumSize(self.minimumSizeHint())

    def choose_dest_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Zielordner auswählen")
        if folder:
            self.dest_path_input.setText(folder)

    def move_files_to_dest(self):
        lm = self.lm
        dest = self.dest_path_input.text().strip()
        if not dest:
            QMessageBox.warning(self, "Fehler", "Bitte Zielpfad angeben oder auswählen.")
            return
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "Fehler", "Keine Dateien in der Liste.")
            return
        dest_path = Path(dest)
        try:
            dest_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Zielordner kann nicht erstellt werden:\n{e}")
            return

        naming_cfg = load_config().get("naming", {})
        folder_pattern = naming_cfg.get("folder", "{artist} - {album}")
        file_pattern = naming_cfg.get("file", "{track} - {artist} - {title}")
        moved = 0
        errors = 0
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            src_str = item.data(Qt.UserRole)
            if not src_str:
                continue
            src = Path(src_str)
            try:
                audio = MP3(str(src), ID3=EasyID3)
            except Exception:
                audio = MP3(str(src))
            tags = {
                "artist": audio.get("artist", [""])[0] or "Unknown_Artist",
                "title": audio.get("title", [""])[0] or "Unknown_Title",
                "album": audio.get("album", [""])[0] or "Unknown_Album",
                "year": audio.get("date", [""])[0][:4] if audio.get("date", [""]) else "",
                "track": audio.get("tracknumber", [""])[0].split("/")[0] if audio.get("tracknumber", [""]) else "",
                "genre": audio.get("genre", [""])[0] or "Unknown_Genre",
                "composer": audio.get("composer", [""])[0] or "",
            }

            def safe(s):
                return re.sub(r'[<>:"/\\|?*]', '_', str(s))

            folder_part = folder_pattern
            for k, v in tags.items():
                folder_part = folder_part.replace("{" + k + "}", safe(v))
            file_part = file_pattern
            for k, v in tags.items():
                file_part = file_part.replace("{" + k + "}", safe(v))
            file_part += src.suffix

            target_dir = dest_path / folder_part
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                errors += 1
                continue
            target = target_dir / file_part
            if target.exists():
                base = target.stem
                cnt = 1
                while target.exists():
                    target = target_dir / f"{base}_{cnt}{src.suffix}"
                    cnt += 1
            try:
                shutil.move(str(src), str(target))
                moved += 1
            except Exception:
                errors += 1

        self.show_toast(f"{moved} Datei(en) verschoben, {errors} Fehler")
        LogManager.instance().info(f"Move: {moved} verschoben, {errors} Fehler nach {dest}")

    def show_toast(self, message, duration=3000):
        if self.isVisible():
            ToastWidget(message, self, duration)

    # --- Player methods ---
    def add_files_to_playlist(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add to Playlist", "", "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a);;All Files (*)")
        for f in files:
            self.player_playlist.append(f)
            self.playlist_list.addItem(Path(f).name)

    def remove_from_playlist(self):
        row = self.playlist_list.currentRow()
        if row >= 0 and row < len(self.player_playlist):
            self.playlist_list.takeItem(row)
            self.player_playlist.pop(row)
            if self.player_current_index == row:
                self.stop_player()
                self.player_current_index = -1
            elif self.player_current_index > row:
                self.player_current_index -= 1

    def clear_playlist(self):
        self.player_playlist.clear()
        self.playlist_list.clear()
        self.stop_player()
        self.player_current_index = -1

    def save_playlist(self):
        if not self.player_playlist:
            QMessageBox.information(self, "Playlist", "Playlist is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "playlist.m3u", "M3U Files (*.m3u)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for fp in self.player_playlist:
                    p = Path(fp)
                    f.write(f"#EXTINF:-1,{p.stem}\n")
                    f.write(f"{fp}\n")
            LogManager.instance().info(f"Playlist saved: {path}")
            self.show_toast(f"Playlist saved ({Path(path).name})")

    def play_selected(self, item):
        row = self.playlist_list.row(item)
        if 0 <= row < len(self.player_playlist):
            self.player_current_index = row
            self._play_current()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.player.playbackState() == QMediaPlayer.PausedState:
            self.player.play()
        elif self.player_playlist:
            if self.player_current_index < 0:
                self.player_current_index = 0
            self._play_current()

    def stop_player(self):
        self.player.stop()
        self.seek_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.now_playing_label.setText("No file selected")
        self.play_btn.setText(">")

    def play_prev(self):
        if self.player_playlist:
            self.player_current_index = (self.player_current_index - 1) % len(self.player_playlist)
            self._play_current()

    def play_next(self):
        if self.player_playlist:
            self.player_current_index = (self.player_current_index + 1) % len(self.player_playlist)
            self._play_current()

    def _play_current(self):
        if 0 <= self.player_current_index < len(self.player_playlist):
            fp = self.player_playlist[self.player_current_index]
            self.player.setSource(QUrl.fromLocalFile(fp))
            self.playlist_list.setCurrentRow(self.player_current_index)
            self.now_playing_label.setText(f"▶ {Path(fp).name}")
            self.player.play()

    def seek_position(self, pos):
        self.player.setPosition(pos)

    def set_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    def on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.play_next()

    def on_position_changed(self, pos):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(pos)
        dur = self.player.duration()
        if dur > 0:
            def fmt(ms):
                s = ms // 1000
                return f"{s // 60:02d}:{s % 60:02d}"
            self.time_label.setText(f"{fmt(pos)} / {fmt(dur)}")

    def on_duration_changed(self, dur):
        self.seek_slider.setRange(0, dur)

    def on_playback_state_changed(self, state):
        self.play_btn.setText("||" if state == QMediaPlayer.PlayingState else ">")

    def open_file_dialog(self):
        lm = self.lm
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            lm.tr("select_file"),
            "",
            f"{lm.tr('mp3_files')} (*.mp3);;{lm.tr('all_files')} (*)"
        )
        if file_path:
            LogManager.instance().info(f"Datei geöffnet: {file_path}")
            self.load_file(file_path)
            self.show_toast(self.lm.tr("status_file_loaded").format(filename=Path(file_path).name))

    def open_folder_dialog(self):
        lm = self.lm
        folder_path = QFileDialog.getExistingDirectory(
            self,
            lm.tr("select_folder")
        )
        if folder_path:
            LogManager.instance().info(f"Ordner geöffnet: {folder_path}")
            self.load_folder(folder_path)

    def open_folder_recursive_dialog(self):
        lm = self.lm
        folder_path = QFileDialog.getExistingDirectory(
            self,
            lm.tr("select_folder")
        )
        if folder_path:
            LogManager.instance().info(f"Ordner (rekursiv) geöffnet: {folder_path}")
            self.load_folder_recursive(folder_path)

    def load_folder(self, folder_path):
        self.file_list.clear()
        self.current_file = None
        self.clear_tag_inputs()
        lm = self.lm

        progress = QProgressDialog(lm.tr("status_processing"), lm.tr("cancel"), 0, 0, self)
        progress.setWindowTitle(lm.tr("select_folder"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)
        progress.setValue(0)
        progress.show()

        result = []

        def worker():
            try:
                files = sorted(Path(folder_path).glob("*.mp3"))
                for f in files:
                    if progress.wasCanceled():
                        break
                    result.append(f)
            finally:
                from PySide6.QtCore import QMetaObject, Qt as QtCore
                QMetaObject.invokeMethod(progress, "close", QtCore.QueuedConnection)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while thread.is_alive():
            QApplication.processEvents()
        thread.join()

        for f in result:
            self.file_list.addItem(str(f.name))
            self.file_list.item(self.file_list.count() - 1).setData(Qt.UserRole, str(f))

        if result:
            self.status_label.setText(f"{len(result)} MP3 {lm.tr('mp3_files').lower()} {lm.tr('status_loaded').lower()}")
            LogManager.instance().info(f"{len(result)} MP3-Dateien geladen aus: {folder_path}")
            self.show_toast(f"{len(result)} {lm.tr('mp3_files')} {lm.tr('status_loaded')}")
        else:
            self.status_label.setText(lm.tr("no_results"))
            LogManager.instance().warning(f"Keine MP3-Dateien gefunden in: {folder_path}")

    def load_folder_recursive(self, folder_path):
        self.file_list.clear()
        self.current_file = None
        self.clear_tag_inputs()
        lm = self.lm

        progress = QProgressDialog(lm.tr("status_processing"), lm.tr("cancel"), 0, 0, self)
        progress.setWindowTitle(lm.tr("select_folder"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)
        progress.setValue(0)
        progress.show()

        result = []

        def worker():
            try:
                files = sorted(Path(folder_path).rglob("*.mp3"))
                for f in files:
                    if progress.wasCanceled():
                        break
                    result.append(f)
            finally:
                from PySide6.QtCore import QMetaObject, Qt as QtCore
                QMetaObject.invokeMethod(progress, "close", QtCore.QueuedConnection)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while thread.is_alive():
            QApplication.processEvents()
        thread.join()

        for f in result:
            rel = f.relative_to(folder_path)
            self.file_list.addItem(str(rel))
            self.file_list.item(self.file_list.count() - 1).setData(Qt.UserRole, str(f))

        if result:
            self.status_label.setText(f"{len(result)} MP3 {lm.tr('mp3_files').lower()} {lm.tr('status_loaded').lower()} (rekursiv)")
            LogManager.instance().info(f"{len(result)} MP3-Dateien rekursiv geladen aus: {folder_path}")
            self.show_toast(f"{len(result)} {lm.tr('mp3_files')} {lm.tr('status_loaded')} (rekursiv)")
        else:
            self.status_label.setText(lm.tr("no_results"))
            LogManager.instance().warning(f"Keine MP3-Dateien rekursiv gefunden in: {folder_path}")

    def load_file(self, file_path):
        self.current_file = file_path
        self.file_list.clear()
        self.file_list.addItem(Path(file_path).name)
        self.file_list.item(0).setData(Qt.UserRole, file_path)
        self.file_list.setCurrentRow(0)
        self.read_tags()

    def on_file_selected(self, item):
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.current_file = file_path
            LogManager.instance().debug(f"Datei aus Liste gewählt: {file_path}")
            self.read_tags()

    def read_tags(self):
        lm = self.lm
        if not self.current_file:
            self.status_label.setText(lm.tr("error_no_file"))
            return

        try:
            audio = MP3(self.current_file, ID3=EasyID3)
            self.title_input.setText(audio.get("title", [""])[0])
            self.artist_input.setText(audio.get("artist", [""])[0])
            self.album_input.setText(audio.get("album", [""])[0])
            self.year_input.setText(audio.get("date", [""])[0])
            self.genre_input.setText(audio.get("genre", [""])[0])
            self.track_input.setText(audio.get("tracknumber", [""])[0])
            self.composer_input.setText(audio.get("composer", [""])[0])
            self.album_artist_input.setText(audio.get("albumartist", [""])[0])

            try:
                comm_frames = audio.tags.getall("COMM")
                if comm_frames:
                    self.comment_input.setText(comm_frames[0].text[0])
                else:
                    self.comment_input.clear()
            except Exception:
                self.comment_input.clear()

            self.status_label.setText(
                lm.tr("status_file_loaded").format(filename=Path(self.current_file).name)
            )
            LogManager.instance().info(f"Tags gelesen von: {Path(self.current_file).name}")
            self.show_toast(lm.tr("success_read"))
        except Exception as e:
            self.status_label.setText(f"{lm.tr('error_read_tags')}: {str(e)}")
            LogManager.instance().error(f"Fehler beim Lesen der Tags von {self.current_file}: {e}")

    def write_tags(self):
        lm = self.lm
        if not self.current_file:
            self.status_label.setText(lm.tr("error_no_file"))
            return

        try:
            try:
                audio = MP3(self.current_file, ID3=EasyID3)
            except ID3NoHeaderError:
                audio = MP3(self.current_file)
                audio.add_tags()
                audio = MP3(self.current_file, ID3=EasyID3)
                LogManager.instance().debug(f"Neue ID3-Struktur erstellt für: {self.current_file}")

            tag_map = {
                "title": self.title_input.text(),
                "artist": self.artist_input.text(),
                "album": self.album_input.text(),
                "date": self.year_input.text(),
                "genre": self.genre_input.text(),
                "tracknumber": self.track_input.text(),
                "composer": self.composer_input.text(),
                "albumartist": self.album_artist_input.text(),
            }
            for key, value in tag_map.items():
                if value:
                    audio[key] = value

            comment_text = self.comment_input.text()
            if comment_text:
                from mutagen.id3 import COMM, ID3
                id3 = ID3(self.current_file)
                id3.delall("COMM")
                id3.add(COMM(encoding=3, lang="ENG", desc="", text=comment_text))
                id3.save()

            audio.save()
            self.status_label.setText(lm.tr("status_tags_written"))
            LogManager.instance().info(f"Tags geschrieben auf: {Path(self.current_file).name}")
            self.show_toast(lm.tr("success_write"))
        except Exception as e:
            self.status_label.setText(f"{lm.tr('error_write_tags')}: {str(e)}")
            LogManager.instance().error(f"Fehler beim Schreiben der Tags auf {self.current_file}: {e}")

    def clear_tags(self):
        lm = self.lm
        if not self.current_file:
            self.status_label.setText(lm.tr("error_no_file"))
            return

        reply = QMessageBox.question(
            self,
            lm.tr("clear_tags"),
            lm.tr("confirm_clear"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.clear_tag_inputs()
            try:
                audio = MP3(self.current_file, ID3=EasyID3)
                audio.delete()
                self.status_label.setText(lm.tr("status_tags_cleared"))
                LogManager.instance().info(f"Tags gelöscht von: {Path(self.current_file).name}")
                self.show_toast(lm.tr("success_clear"))
            except Exception as e:
                self.status_label.setText(f"{lm.tr('error_write_tags')}: {str(e)}")
                LogManager.instance().error(f"Fehler beim Löschen der Tags von {self.current_file}: {e}")

    def clear_tag_inputs(self):
        self.title_input.clear()
        self.artist_input.clear()
        self.album_input.clear()
        self.year_input.clear()
        self.genre_input.clear()
        self.track_input.clear()
        self.comment_input.clear()
        self.composer_input.clear()
        self.album_artist_input.clear()

    def open_settings(self):
        LogManager.instance().debug("Einstellungen geöffnet")
        dlg = SettingsDialog(self)
        dlg.language_changed.connect(self.apply_language)
        dlg.exec()

    def refresh_source_combo(self):
        self.source_combo.clear()
        sources = get_sources()
        for key, src in sources.items():
            self.source_combo.addItem(src.get("label", key), key)

    def search_online(self):
        lm = self.lm
        dlg = SearchOnlineDialog(self, preselected_source=self.source_combo.currentData())
        if dlg.exec() == QDialog.Accepted and dlg.selected_tags:
            tags = dlg.selected_tags
            self.title_input.setText(tags.get("title", ""))
            self.artist_input.setText(tags.get("artist", ""))
            self.album_input.setText(tags.get("album", ""))
            self.year_input.setText(tags.get("year", ""))
            self.status_label.setText(
                lm.tr("status_tags_read") + f" ({tags.get('title', '')})"
            )
            LogManager.instance().info(
                f"Online-Suche: {tags.get('artist', '?')} - {tags.get('title', '?')} "
                f"aus {tags.get('album', '?')} ({tags.get('year', '?')})"
            )
            self.show_toast(f"{lm.tr('status_tags_read')}: {tags.get('title', '')}")

    def show_about(self):
        LogManager.instance().debug("Über-Dialog geöffnet")
        dlg = AboutDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        lm = self.lm
        reply = QMessageBox.question(
            self,
            lm.tr("exit"),
            lm.tr("confirm_exit"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            LogManager.instance().info("Programm beendet")
            event.accept()
        else:
            LogManager.instance().debug("Programmende abgebrochen")
            event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    cfg = load_config()
    LogManager.instance().info(f"Log-Level: {LogManager.instance().level}")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
