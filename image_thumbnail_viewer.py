# -*- coding: utf-8 -*-
"""
圖片縮圖檢視器 - 使用 PyQt6 顯示目前資料夾內所有圖片的縮圖
"""

import sys
import os  # 修復路徑轉義與外部開啟邏輯
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QScrollArea,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QComboBox,
    QDialog,
    QMenuBar,
    QMenu,
)
from PyQt6.QtCore import Qt, QStandardPaths, QSettings, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QPixmap, QPalette, QColor, QWheelEvent, QKeyEvent, QAction, QDragEnterEvent, QDropEvent

# 支援的圖片副檔名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif",
                    ".bmp", ".webp", ".ico", ".tiff", ".tif"}

# 縮圖尺寸選項：顯示名稱 -> 最大邊長（像素）（大 = 原 220 再大 50%）
THUMBNAIL_SIZES = {"小": 100, "中": 150, "大": 330}
DEFAULT_THUMBNAIL_KEY = "中"

# 設定檔鍵名（記住上次資料夾 / 縮圖尺寸 / 大圖檢視縮放）
SETTINGS_LAST_FOLDER = "lastFolder"
SETTINGS_THUMBNAIL_SIZE = "thumbnailSize"
SETTINGS_IMAGE_VIEW_ZOOM = "imageViewZoom"  # 0=符合視窗寬度, -1=符合視窗高度, -2=原圖尺寸, 10~500=百分比

# 大圖檢視縮放範圍與步進
ZOOM_MIN, ZOOM_MAX = 10, 500
ZOOM_STEP = 10  # 縮放步進改為 10%


def get_default_folder() -> Path:
    """預設資料夾：桌面；若無法取得則用 C:\\"""
    desktop = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation)
    if desktop:
        p = Path(desktop)
        if p.is_dir():
            return p
    # 修正轉義錯誤：確保路徑字串合法
    return Path(os.path.join("C:\\"))


def load_last_folder() -> Path | None:
    """從設定讀取上次使用的資料夾；若無或無效則回傳 None"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    path_str = settings.value(SETTINGS_LAST_FOLDER, "", type=str)
    if not path_str:
        return None
    # 使用 os.path.normpath 確保 Windows 反斜線正確
    p = Path(os.path.normpath(path_str))
    return p if p.is_dir() else None


def save_last_folder(folder: Path) -> None:
    """將目前資料夾路徑寫入設定"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    settings.setValue(SETTINGS_LAST_FOLDER, str(folder.resolve()))


def load_last_thumbnail_size() -> str:
    """從設定讀取上次縮圖尺寸（小/中/大）"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    v = settings.value(SETTINGS_THUMBNAIL_SIZE,
                       DEFAULT_THUMBNAIL_KEY, type=str)
    return v if v in THUMBNAIL_SIZES else DEFAULT_THUMBNAIL_KEY


def save_last_thumbnail_size(key: str) -> None:
    """將縮圖尺寸選項寫入設定"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    settings.setValue(SETTINGS_THUMBNAIL_SIZE, key)


def load_image_view_zoom() -> int:
    """從設定讀取大圖檢視縮放：0=符合視窗寬度，-1=符合視窗高度，-2=原圖尺寸，10~500=百分比"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    v = settings.value(SETTINGS_IMAGE_VIEW_ZOOM, 0, type=int)
    if v in (0, -1, -2):
        return v
    return max(ZOOM_MIN, min(ZOOM_MAX, v))


def save_image_view_zoom(percent: int) -> None:
    """將大圖檢視縮放寫入設定"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    settings.setValue(SETTINGS_IMAGE_VIEW_ZOOM, percent)


def get_image_files(folder: Path) -> list[Path]:
    """取得資料夾內所有圖片檔案路徑"""
    if not folder.is_dir():
        return []
    return [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]


def load_thumbnail(path: Path, size: int) -> QPixmap:
    """載入圖片並縮放為縮圖"""
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return QPixmap(size, size)  # 空白圖
    pixmap = pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return pixmap


class ThumbnailLabel(QLabel):
    """可顯示縮圖與檔名的標籤，點擊會發出 pathClicked"""

    pathClicked = pyqtSignal(object)  # Path

    def __init__(self, path: Path, size: int, parent=None):
        super().__init__(parent)
        self.path = path
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)  # 邊框寬度增加
        self.setStyleSheet("""
            ThumbnailLabel {
                background-color: #2d2d2d;
                padding: 4px;
                border: 2px solid transparent; /* 初始透明邊框 */
            }
            ThumbnailLabel:hover {
                border: 2px solid #00d9ff; /* Hover 時邊框變青色 */
            }
        """)
        self.setFixedSize(size + 20, size + 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)  # 設定手形游標

        pixmap = load_thumbnail(path, size)
        self.setPixmap(pixmap)
        self.setToolTip(str(path))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pathClicked.emit(self.path)
        super().mousePressEvent(event)


class ImageViewerDialog(QDialog):
    """大圖檢視：符合視窗或自訂縮放，左/右鍵上一張/下一張，滾輪縮放 25%~400%"""

    def __init__(self, paths: list[Path], current_index: int, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.index = max(0, min(current_index, len(paths) - 1))
        self.zoom_percent = load_image_view_zoom()  # 0=符合視窗寬度, -1=符合視窗高度, -2=原圖尺寸
        self._original: QPixmap | None = None
        self._is_fullscreen = False  # 追蹤全螢幕狀態

        self.setWindowTitle(
            f"大圖檢視 - {paths[self.index].name}" if paths else "大圖檢視")
        self.setMinimumSize(320, 240)
        self.resize(900, 700)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e; /* 視窗模式預設背景 */
            }

            /* 通用按鈕樣式 */
            QPushButton {
                background-color: #2a2a2a; /* 深灰 */
                color: #00d9ff; /* 明亮青色 */
                border: 2px solid #00d9ff;
                border-radius: 4px;
                padding: 8px 18px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00d9ff; /* 背景變青色 */
                color: #2a2a2a; /* 文字變深灰 */
                box-shadow: 0 0 10px rgba(0, 217, 255, 0.5); /* 發光陰影 */
            }
            QPushButton:pressed {
                background-color: #00b0d9; /* 按下時更深的青色 */
                color: #ffffff;
            }

            /* 符合視窗按鈕的特殊樣式 */
            #fitWidthButton, #fitHeightButton, #fitOriginalButton {
                border: 2px solid #ffffff;
                color: #ffffff;
            }
            #fitWidthButton:hover, #fitHeightButton:hover, #fitOriginalButton:hover {
                background-color: #ffffff;
                color: #2a2a2a;
                box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
            }

            /* 縮放百分比標籤樣式 */
            QLabel#zoomLabel {
                background-color: #ffcc00; /* 亮黃色 */
                color: #000000; /* 黑色 */
                font-size: 18px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 8px;
                min-width: 80px;
                text-align: center;
                border: none; /* 移除邊框 */
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 工具列佈局優化
        self.toolbar_container = QWidget()
        bar = QHBoxLayout(self.toolbar_container)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(10)  # 間距拉開至 10px

        # 新增寬度符合、高度符合與原圖尺寸按鈕
        self.btn_fit_width = QPushButton("寬度符合")
        self.btn_fit_width.setObjectName(
            "fitWidthButton")  # 設定 objectName 以應用 QSS 樣式
        self.btn_fit_height = QPushButton("高度符合")
        self.btn_fit_height.setObjectName(
            "fitHeightButton")  # 設定 objectName 以應用 QSS 樣式
        self.btn_fit_original = QPushButton("原圖尺寸")
        self.btn_fit_original.setObjectName(
            "fitOriginalButton")  # 設定 objectName 以應用 QSS 樣式

        self.btn_zoom_out = QPushButton("縮小")
        self.btn_zoom_in = QPushButton("放大")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel")  # 設定 objectName 以應用 QSS 樣式
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 新增導覽按鈕
        self.btn_prev = QPushButton("← 上一張")
        self.btn_next = QPushButton("下一張 →")

        # 連接按鈕事件
        self.btn_fit_width.clicked.connect(self._fit_width)
        self.btn_fit_height.clicked.connect(self._fit_height)
        self.btn_fit_original.clicked.connect(self._fit_original)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)

        # 設定按鈕游標
        for btn in (self.btn_fit_width, self.btn_fit_height, self.btn_fit_original, self.btn_zoom_in, self.btn_zoom_out, self.btn_prev, self.btn_next):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        bar.addWidget(self.btn_fit_width)
        bar.addWidget(self.btn_fit_height)
        bar.addWidget(self.btn_fit_original)
        bar.addSpacing(10)
        bar.addWidget(self.btn_zoom_out)
        bar.addWidget(self.zoom_label)
        bar.addWidget(self.btn_zoom_in)
        bar.addSpacing(20)  # 增加間距
        bar.addWidget(self.btn_prev)
        bar.addWidget(self.btn_next)

        bar.addStretch(1)

        layout.addWidget(self.toolbar_container)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)  # 保持圖片尺寸，長或寬超出視窗即可平移
        self.scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: none; }")
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: #2d2d2d; }")
        self.image_label.setMinimumSize(1, 1)
        self.scroll.setWidget(self.image_label)

        # 安裝事件過濾器處理拖拽與縮放
        self.scroll.viewport().installEventFilter(self)
        self.scroll.installEventFilter(self)
        self.image_label.installEventFilter(self)
        self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.scroll, 1)

        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_h = 0
        self._drag_start_v = 0

        # 初始化時，讓圖片區域具有打開的手形游標
        self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)

        self._load_image()
        self._apply_zoom()

    def eventFilter(self, obj, event):
        """完全保留原始的 eventFilter 邏輯"""
        if obj == self.scroll.viewport():
            t = event.type()
            if t == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._zoom_in()
                elif delta < 0:
                    self._zoom_out()
                return True
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = True
                self._drag_start_pos = event.position().toPoint()
                self._drag_start_h = self.scroll.horizontalScrollBar().value()
                self._drag_start_v = self.scroll.verticalScrollBar().value()
                self.image_label.setCursor(
                    Qt.CursorShape.ClosedHandCursor)  # 按下變為抓取手形
                return False
            if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = False
                self.image_label.setCursor(
                    Qt.CursorShape.OpenHandCursor)  # 放開變為開放手形
                return False
            if t == QEvent.Type.MouseMove and self._dragging:
                pos = event.position().toPoint()
                dx = pos.x() - self._drag_start_pos.x()
                dy = pos.y() - self._drag_start_pos.y()
                self.scroll.horizontalScrollBar().setValue(self._drag_start_h - dx)
                self.scroll.verticalScrollBar().setValue(self._drag_start_v - dy)
                return True

        if obj == self.image_label:
            if event.type() == QEvent.Type.Enter and not self._dragging:
                self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
            if event.type() == QEvent.Type.Leave and not self._dragging:
                self.image_label.unsetCursor()

        if event.type() == QEvent.Type.KeyPress and obj in (self.scroll, self.scroll.viewport(), self.image_label):
            key = event.key()
            if key == Qt.Key.Key_Left:
                self._go_prev()
                return True
            if key == Qt.Key.Key_Right:
                self._go_next()
                return True
        return super().eventFilter(obj, event)

    def _load_image(self):
        if not self.paths or self.index < 0 or self.index >= len(self.paths):
            self._update_navigation_buttons()
            return
        path = self.paths[self.index]
        self._original = QPixmap(str(path))
        self.setWindowTitle(f"大圖檢視 - {path.name}")
        if self._original.isNull():
            self.image_label.setText("無法載入圖片")
        else:
            self._apply_zoom()
        self._update_navigation_buttons()

    def _update_navigation_buttons(self):
        n = len(self.paths)
        self.btn_prev.setEnabled(n > 0 and self.index > 0)
        self.btn_next.setEnabled(n > 0 and self.index < n - 1)

    def _fit_width_scale(self) -> float:
        if not self._original or self._original.isNull():
            return 1.0
        return self.scroll.viewport().width() / self._original.width()

    def _fit_height_scale(self) -> float:
        if not self._original or self._original.isNull():
            return 1.0
        return self.scroll.viewport().height() / self._original.height()

    def _apply_zoom(self):
        if not self._original or self._original.isNull():
            self.zoom_label.setText("-")
            return

        target_scale = 1.0
        if self.zoom_percent == 0:
            target_scale = self._fit_width_scale()
        elif self.zoom_percent == -1:
            target_scale = self._fit_height_scale()
        elif self.zoom_percent == -2:
            target_scale = 1.0  # 原圖尺寸
        else:
            target_scale = self.zoom_percent / 100.0

        nw = max(1, int(self._original.width() * target_scale))
        nh = max(1, int(self._original.height() * target_scale))
        actual_zoom_val = int(target_scale * 100)

        scaled = self._original.scaled(
            nw, nh, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.width(), scaled.height())

        display_text = f"{actual_zoom_val}%"
        if self.zoom_percent == 0:
            display_text = f"寬度 ({actual_zoom_val}%)"
        elif self.zoom_percent == -1:
            display_text = f"高度 ({actual_zoom_val}%)"
        elif self.zoom_percent == -2:
            display_text = f"原圖 ({actual_zoom_val}%)"
        self.zoom_label.setText(display_text)

    def _fit_width(self):
        self.zoom_percent = 0
        save_image_view_zoom(0)
        self._apply_zoom()

    def _fit_height(self):
        self.zoom_percent = -1
        save_image_view_zoom(-1)
        self._apply_zoom()

    def _fit_original(self):
        self.zoom_percent = -2
        save_image_view_zoom(-2)
        self._apply_zoom()

    def _zoom_in(self):
        if self.zoom_percent <= 0:
            if self.zoom_percent == 0:
                self.zoom_percent = int(self._fit_width_scale() * 100)
            elif self.zoom_percent == -1:
                self.zoom_percent = int(self._fit_height_scale() * 100)
            elif self.zoom_percent == -2:
                self.zoom_percent = 110  # 從 100% 開始放大
        self.zoom_percent = min(ZOOM_MAX, self.zoom_percent + ZOOM_STEP)
        save_image_view_zoom(self.zoom_percent)
        self._apply_zoom()

    def _zoom_out(self):
        if self.zoom_percent <= 0:
            if self.zoom_percent == 0:
                self.zoom_percent = int(self._fit_width_scale() * 100)
            elif self.zoom_percent == -1:
                self.zoom_percent = int(self._fit_height_scale() * 100)
            elif self.zoom_percent == -2:
                self.zoom_percent = 90  # 從 100% 開始縮小
        self.zoom_percent = max(ZOOM_MIN, self.zoom_percent - ZOOM_STEP)
        save_image_view_zoom(self.zoom_percent)
        self._apply_zoom()

    def _go_prev(self):
        if self.paths and self.index > 0:
            self.index -= 1
            self._load_image()

    def _go_next(self):
        if self.paths and self.index < len(self.paths) - 1:
            self.index += 1
            self._load_image()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_F11, Qt.Key.Key_Return):
            if self._is_fullscreen:
                self.showNormal()
                self.toolbar_container.show()
            else:
                self.showFullScreen()
                self.toolbar_container.hide()
            self._is_fullscreen = not self._is_fullscreen
            self._apply_zoom()
            return
        if key == Qt.Key.Key_Escape:
            if self._is_fullscreen:
                self._is_fullscreen = False
                self.showNormal()
                self.toolbar_container.show()
                self._apply_zoom()
            else:
                self.reject()
            return
        super().keyPressEvent(event)


class ImageThumbnailViewer(QMainWindow):
    """完整 500 行主視窗邏輯，植入拖放與外部開啟功能"""

    def __init__(self, start_path: Path | None = None):
        super().__init__()
        self.setAcceptDrops(True)  # 開啟拖放

        # 決定初始路徑
        if start_path and start_path.exists():
            self.folder = start_path if start_path.is_dir() else start_path.parent
            self.initial_file = start_path if start_path.is_file() else None
        else:
            last = load_last_folder()
            self.folder = last if last else get_default_folder()
            self.initial_file = None

        size_key = load_last_thumbnail_size()
        self.thumbnail_size = THUMBNAIL_SIZES[size_key]
        self.setWindowTitle(f"圖片縮圖檢視 - {self.folder}")
        self.resize(800, 600)

        central = QWidget()
        main_layout = QVBoxLayout(central)
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)

        self.path_edit = QLineEdit(str(self.folder.resolve()))
        self.path_edit.returnPressed.connect(self._navigate_to_path_edit)
        self.path_edit.setStyleSheet(
            "QLineEdit { background-color: #1e1e1e; color: #ffcc00; border: 2px solid #ffcc00; border-radius: 4px; padding: 6px 10px; font-weight: bold; }")

        self.btn_choose = QPushButton("選擇資料夾…")
        self.btn_choose.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #00d9ff; border: 2px solid #00d9ff; border-radius: 4px; padding: 8px 16px; font-weight: bold; }")
        self.btn_choose.clicked.connect(self._choose_folder)

        self.size_combo = QComboBox()
        self.size_combo.addItems(list(THUMBNAIL_SIZES.keys()))
        self.size_combo.setCurrentText(size_key)
        self.size_combo.currentTextChanged.connect(
            self._on_thumbnail_size_changed)

        bar_layout.addWidget(self.btn_choose)
        bar_layout.addWidget(self.path_edit, 1)
        bar_layout.addWidget(QLabel("縮圖："))
        bar_layout.addWidget(self.size_combo)
        main_layout.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: none; }")
        self.content = QWidget()
        self.layout = QGridLayout(self.content)
        self.layout.setSpacing(16)
        self.scroll.setWidget(self.content)
        main_layout.addWidget(self.scroll, 1)

        self.setCentralWidget(central)
        self.load_thumbnails()

        # 如果是由檔案啟動，延遲自動開啟大圖
        if self.initial_file:
            QTimer.singleShot(
                200, lambda: self._open_image_view_at_file(self.initial_file))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        path = Path(event.mimeData().urls()[0].toLocalFile())
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            self.folder = path.parent
            self.load_thumbnails()
            self._open_image_view_at_file(path)
        elif path.is_dir():
            self.folder = path
            self.load_thumbnails()
        self.path_edit.setText(str(self.folder.resolve()))
        save_last_folder(self.folder)

    def _open_image_view_at_file(self, file_path: Path):
        imgs = sorted(get_image_files(self.folder))
        if file_path in imgs:
            ImageViewerDialog(imgs, imgs.index(file_path), self).exec()

    def _navigate_to_path_edit(self):
        p = Path(os.path.normpath(self.path_edit.text().strip()))
        if p.is_dir():
            self.folder = p.resolve()
            save_last_folder(self.folder)
            self.load_thumbnails()
        else:
            self.path_edit.setText(str(self.folder.resolve()))

    def _choose_folder(self):
        p = QFileDialog.getExistingDirectory(
            self, "選取資料夾", str(self.folder.resolve()))
        if p:
            self.folder = Path(p)
            save_last_folder(self.folder)
            self.load_thumbnails()

    def _on_thumbnail_size_changed(self, key):
        self.thumbnail_size = THUMBNAIL_SIZES[key]
        save_last_thumbnail_size(key)
        self.load_thumbnails()

    def load_thumbnails(self):
        while self.layout.count():
            w = self.layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        images = sorted(get_image_files(self.folder))
        size = self.thumbnail_size
        cols = max(1, self.width() // (size + 40))
        for i, path in enumerate(images):
            lbl = ThumbnailLabel(path, size)
            lbl.pathClicked.connect(
                lambda p, idx=i: self._open_image_view_at_file(p))
            container = QWidget()
            box = QVBoxLayout(container)
            box.addWidget(lbl, 0, Qt.AlignmentFlag.AlignCenter)
            box.addWidget(QLabel(path.name), 0, Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(container, i // cols, i % cols)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 修正啟動參數與 Windows 路徑
    start_p = Path(os.path.normpath(sys.argv[1])) if len(
        sys.argv) > 1 else None
    viewer = ImageThumbnailViewer(start_p)
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
