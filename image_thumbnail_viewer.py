"""
圖片縮圖檢視器 - 使用 PyQt6 顯示目前資料夾內所有圖片的縮圖
"""

import sys
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
from PyQt6.QtCore import Qt, QStandardPaths, QSettings, pyqtSignal, QEvent
from PyQt6.QtGui import QPixmap, QPalette, QColor, QWheelEvent, QKeyEvent, QAction

# 支援的圖片副檔名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}

# 縮圖尺寸選項：顯示名稱 -> 最大邊長（像素）（大 = 原 220 再大 50%）
THUMBNAIL_SIZES = {"小": 100, "中": 150, "大": 330}
DEFAULT_THUMBNAIL_KEY = "中"

# 設定檔鍵名（記住上次資料夾 / 縮圖尺寸 / 大圖檢視縮放）
SETTINGS_LAST_FOLDER = "lastFolder"
SETTINGS_THUMBNAIL_SIZE = "thumbnailSize"
SETTINGS_IMAGE_VIEW_ZOOM = "imageViewZoom"  # 0=符合視窗, 25~400=百分比

# 大圖檢視縮放範圍與步進
ZOOM_MIN, ZOOM_MAX = 10, 500
ZOOM_STEP = 10 # 縮放步進改為 10%

def get_default_folder() -> Path:
    """預設資料夾：桌面；若無法取得則用 C:\\"""

    desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    if desktop:
        p = Path(desktop)
        if p.is_dir():
            return p
    return Path("C:\\")


def load_last_folder() -> Path | None:
    """從設定讀取上次使用的資料夾；若無或無效則回傳 None"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    path_str = settings.value(SETTINGS_LAST_FOLDER, "", type=str)
    if not path_str:
        return None
    p = Path(path_str)
    return p if p.is_dir() else None


def save_last_folder(folder: Path) -> None:
    """將目前資料夾路徑寫入設定"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    settings.setValue(SETTINGS_LAST_FOLDER, str(folder.resolve()))


def load_last_thumbnail_size() -> str:
    """從設定讀取上次縮圖尺寸（小/中/大）"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    v = settings.value(SETTINGS_THUMBNAIL_SIZE, DEFAULT_THUMBNAIL_KEY, type=str)
    return v if v in THUMBNAIL_SIZES else DEFAULT_THUMBNAIL_KEY


def save_last_thumbnail_size(key: str) -> None:
    """將縮圖尺寸選項寫入設定"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    settings.setValue(SETTINGS_THUMBNAIL_SIZE, key)


def load_image_view_zoom() -> int:
    """從設定讀取大圖檢視縮放：0=符合視窗，25~400=百分比"""
    settings = QSettings("ImgSee", "ImageThumbnailViewer")
    v = settings.value(SETTINGS_IMAGE_VIEW_ZOOM, 0, type=int)
    if v == 0:
        return 0
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
        self.setLineWidth(2) # 邊框寬度增加
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
        self.setCursor(Qt.CursorShape.PointingHandCursor) # 設定手形游標

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
        self.zoom_percent = load_image_view_zoom()  # 0 = 符合視窗
        self._original: QPixmap | None = None
        self.setWindowTitle(f"大圖檢視 - {paths[self.index].name}" if paths else "大圖檢視")
        self.setMinimumSize(320, 240)
        self.resize(900, 700)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }

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
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #555555;
                border-color: #333;
                box-shadow: none;
            }

            /* 符合視窗按鈕的特殊樣式 */
            #fitWidthButton, #fitHeightButton {
                border: 2px solid #ffffff;
                color: #ffffff;
            }
            #fitWidthButton:hover, #fitHeightButton:hover {
                background-color: #ffffff;
                color: #2a2a2a;
                box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
            }
            #fitWidthButton:pressed, #fitHeightButton:pressed {
                background-color: #cccccc;
                color: #2a2a2a;
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
        toolbar_container = QWidget()
        # toolbar_container.setStyleSheet("background-color: #1e1e1e;") # 樣式已整合至主 QDialog
        bar = QHBoxLayout(toolbar_container)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(10) # 間距拉開至 10px

        # 新增寬度符合與高度符合按鈕
        self.btn_fit_width = QPushButton("寬度符合")
        self.btn_fit_width.setObjectName("fitWidthButton") # 設定 objectName 以應用 QSS 樣式
        self.btn_fit_height = QPushButton("高度符合")
        self.btn_fit_height.setObjectName("fitHeightButton") # 設定 objectName 以應用 QSS 樣式

        self.btn_zoom_out = QPushButton("縮小")
        self.btn_zoom_in = QPushButton("放大")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel") # 設定 objectName 以應用 QSS 樣式
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 新增導覽按鈕
        self.btn_prev = QPushButton("← 上一張")
        self.btn_next = QPushButton("下一張 →")
        
        # 連接按鈕事件
        self.btn_fit_width.clicked.connect(self._fit_width)
        self.btn_fit_height.clicked.connect(self._fit_height)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)

        # 設定按鈕游標
        for btn in (self.btn_fit_width, self.btn_fit_height, self.btn_zoom_in, self.btn_zoom_out, self.btn_prev, self.btn_next):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        bar.addWidget(self.btn_fit_width)
        bar.addWidget(self.btn_fit_height)
        bar.addSpacing(10)
        bar.addWidget(self.btn_zoom_out)
        bar.addWidget(self.zoom_label)
        bar.addWidget(self.btn_zoom_in)
        bar.addSpacing(20) # 增加間距
        bar.addWidget(self.btn_prev)
        bar.addWidget(self.btn_next)
        
        bar.addStretch(1)
        
        layout.addWidget(toolbar_container)

        self.scroll = QScrollArea()


        self.scroll.setWidgetResizable(False)  # 保持圖片尺寸，長或寬超出視窗即可平移
        self.scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: none; }")
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: #2d2d2d; }")
        self.image_label.setMinimumSize(1, 1)
        self.scroll.setWidget(self.image_label)
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
        """捲動區域：滾輪縮放；鍵盤左/右上一張/下一張；按住拖曳平移圖片；游標控制"""
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
                self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor) # 按下變為抓取手形
                return False
            if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = False
                self.image_label.setCursor(Qt.CursorShape.OpenHandCursor) # 放開變為開放手形
                return False
            if t == QEvent.Type.MouseMove and self._dragging:
                pos = event.position().toPoint()
                dx = pos.x() - self._drag_start_pos.x()
                dy = pos.y() - self._drag_start_pos.y()
                h_bar = self.scroll.horizontalScrollBar()
                v_bar = self.scroll.verticalScrollBar()
                new_h = self._drag_start_h - dx
                new_v = self._drag_start_v - dy
                h_bar.setValue(max(h_bar.minimum(), min(h_bar.maximum(), new_h)))
                v_bar.setValue(max(v_bar.minimum(), min(v_bar.maximum(), new_v)))
                return True
        
        # 處理圖片標籤的游標事件
        if obj == self.image_label:
            if event.type() == QEvent.Type.Enter:
                if not self._dragging:
                    self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
                return False
            if event.type() == QEvent.Type.Leave:
                if not self._dragging:
                    self.image_label.unsetCursor() # 離開時恢復預設游標
                return False

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
            self.image_label.clear()
            self.image_label.setText("無法載入圖片")
            self._update_navigation_buttons()
            return
        self._apply_zoom()
        self._update_navigation_buttons()

    def _update_navigation_buttons(self):
        """依目前索引更新導覽按鈕可否點擊"""
        n = len(self.paths)
        self.btn_prev.setEnabled(n > 0 and self.index > 0)
        self.btn_next.setEnabled(n > 0 and self.index < n - 1)

    def _fit_width_scale(self) -> float:
        """計算符合視窗寬度的縮放比例"""
        if not self._original or self._original.isNull():
            return 1.0
        vp_w = self.scroll.viewport().width()
        ow = self._original.width()
        if ow <= 0: return 1.0
        return vp_w / ow
    
    def _fit_height_scale(self) -> float:
        """計算符合視窗高度的縮放比例"""
        if not self._original or self._original.isNull():
            return 1.0
        vp_h = self.scroll.viewport().height()
        oh = self._original.height()
        if oh <= 0: return 1.0
        return vp_h / oh

    def _apply_zoom(self):
        if not self._original or self._original.isNull():
            self.zoom_label.setText("-")
            return
        ow, oh = self._original.width(), self._original.height()
        
        target_scale = 1.0
        if self.zoom_percent == 0: # 寬度符合
            target_scale = self._fit_width_scale()
        elif self.zoom_percent == -1: # 高度符合
            target_scale = self._fit_height_scale()
        else: # 自訂縮放
            target_scale = self.zoom_percent / 100.0

        nw = max(1, int(ow * target_scale))
        nh = max(1, int(oh * target_scale))
        
        # 更新 zoom_percent 以反映實際縮放值，限制在 ZOOM_MIN ~ ZOOM_MAX 範圍
        actual_zoom_val = int(target_scale * 100)
        self.zoom_percent_display = max(ZOOM_MIN, min(ZOOM_MAX, actual_zoom_val))
        
        scaled = self._original.scaled(
            nw, nh,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.width(), scaled.height())

        # 更新百分比標籤
        if self.zoom_percent == 0:
            self.zoom_label.setText(f"寬度 ({self.zoom_percent_display}%)")
        elif self.zoom_percent == -1:
            self.zoom_label.setText(f"高度 ({self.zoom_percent_display}%)")
        else:
            self.zoom_label.setText(f"{self.zoom_percent_display}%")

    def _fit_width(self):
        self.zoom_percent = 0  # 0 代表寬度符合
        save_image_view_zoom(0)
        self._apply_zoom()
    
    def _fit_height(self):
        self.zoom_percent = -1 # -1 代表高度符合
        save_image_view_zoom(-1)
        self._apply_zoom()

    def _zoom_in(self):
        if self.zoom_percent == 0: # 從寬度符合開始放大
            self.zoom_percent = max(ZOOM_MIN, int(self._fit_width_scale() * 100))
        elif self.zoom_percent == -1: # 從高度符合開始放大
            self.zoom_percent = max(ZOOM_MIN, int(self._fit_height_scale() * 100))
        self.zoom_percent = min(ZOOM_MAX, self.zoom_percent + ZOOM_STEP)
        save_image_view_zoom(self.zoom_percent)
        self._apply_zoom()

    def _zoom_out(self):
        if self.zoom_percent == 0: # 從寬度符合開始縮小
            self.zoom_percent = max(ZOOM_MIN, int(self._fit_width_scale() * 100))
        elif self.zoom_percent == -1: # 從高度符合開始縮小
            self.zoom_percent = max(ZOOM_MIN, int(self._fit_height_scale() * 100))
        self.zoom_percent = max(ZOOM_MIN, self.zoom_percent - ZOOM_STEP)
        save_image_view_zoom(self.zoom_percent)
        self._apply_zoom()

    def _go_prev(self):
        if not self.paths or self.index <= 0:
            return
        self.index -= 1
        self._load_image()

    def _go_next(self):
        if not self.paths or self.index >= len(self.paths) - 1:
            return
        self.index += 1
        self._load_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_percent == 0 or self.zoom_percent == -1:
            self._apply_zoom()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Left:
            self._go_prev()
            return
        if key == Qt.Key.Key_Right:
            self._go_next()
            return
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.reject()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom_in()
        elif delta < 0:
            self._zoom_out()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus(Qt.FocusReason.OtherFocusReason)



class ImageThumbnailViewer(QMainWindow):
    """主視窗：顯示目前資料夾內所有圖片縮圖，可像檔案總管選擇資料夾"""

    def __init__(self, folder: Path | None = None):
        super().__init__()
        if folder is not None:
            self.folder = folder
        else:
            last = load_last_folder()
            self.folder = last if last is not None else get_default_folder()
        size_key = load_last_thumbnail_size()
        self.thumbnail_size = THUMBNAIL_SIZES[size_key]
        self.setWindowTitle(f"圖片縮圖檢視 - {self.folder}")
        self.setMinimumSize(500, 400)
        self.resize(800, 600)

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 上方：目錄選擇列（路徑 + 選擇資料夾按鈕）
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(10) # 間距調整為 10px

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("輸入或貼上資料夾路徑，按 Enter 切換")
        self.path_edit.setText(str(self.folder.resolve()))
        self.path_edit.returnPressed.connect(self._navigate_to_path_edit)
        self.path_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e; /* 極深灰 */
                color: #ffcc00; /* 亮黃色 */
                border: 2px solid #ffcc00;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self.path_edit.setCursor(Qt.CursorShape.IBeamCursor) # 輸入框保持 IBeamCursor

        self.btn_choose = QPushButton("選擇資料夾…")
        self.btn_choose.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a; /* 深灰 */
                color: #00d9ff; /* 明亮青色 */
                border: 2px solid #00d9ff;
                border-radius: 4px;
                padding: 8px 16px;
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
        """)
        self.btn_choose.clicked.connect(self._choose_folder)
        self.btn_choose.setCursor(Qt.CursorShape.PointingHandCursor)

        self.size_combo = QComboBox()
        self.size_combo.addItems(list(THUMBNAIL_SIZES.keys()))
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentText(size_key)
        self.size_combo.blockSignals(False)
        self.size_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a; /* 深灰 */
                color: #ffffff; /* 白色 */
                border: 2px solid #ffffff;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
                font-weight: bold;
            }
            QComboBox:hover { 
                border-color: #00d9ff; /* Hover 時邊框變青色 */
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a; /* 深灰 */
                color: #ffffff; /* 白色 */
                selection-background-color: #00d9ff; /* 選取背景青色 */
                selection-color: #2a2a2a; /* 選取文字深灰 */
                outline: none;
                border: 1px solid #00d9ff;
            }
        """)
        # 下拉選單底色與字色（避免白底白字看不到）
        popup_view = self.size_combo.view()
        pal = popup_view.palette()
        pal.setColor(pal.ColorRole.Base, QColor(0x2a, 0x2a, 0x2a)) # 背景
        pal.setColor(pal.ColorRole.Text, QColor(0xff, 0xff, 0xff)) # 文字
        pal.setColor(pal.ColorRole.Highlight, QColor(0x00, 0xd9, 0xff)) # 選取背景
        pal.setColor(pal.ColorRole.HighlightedText, QColor(0x2a, 0x2a, 0x2a)) # 選取文字
        popup_view.setPalette(pal)
        self.size_combo.currentTextChanged.connect(self._on_thumbnail_size_changed)
        self.size_combo.setCursor(Qt.CursorShape.PointingHandCursor)

        # 佈局順序調整
        bar_layout.addWidget(self.btn_choose)
        bar_layout.addWidget(self.path_edit, 1)
        bar_layout.addWidget(QLabel("縮圖："))
        bar_layout.addWidget(self.size_combo)

        main_layout.addWidget(bar)


        # 捲動區域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: none; }")

        self.content = QWidget()
        self.layout = QGridLayout(self.content)
        self.layout.setSpacing(16)

        scroll.setWidget(self.content)
        main_layout.addWidget(scroll, 1)

        self.setCentralWidget(central)

        self.load_thumbnails()

    def _navigate_to_path_edit(self):
        """依路徑欄位內容切換資料夾（Enter 時呼叫）"""
        path_str = self.path_edit.text().strip()
        if not path_str:
            return
        p = Path(path_str)
        if not p.is_dir():
            self.path_edit.setText(str(self.folder.resolve()))  # 還原為目前路徑
            return
        self.folder = p.resolve()
        save_last_folder(self.folder)
        self.setWindowTitle(f"圖片縮圖檢視 - {self.folder}")
        self.path_edit.setText(str(self.folder))
        self._clear_thumbnails()
        self.load_thumbnails()

    def _choose_folder(self):
        """開啟像檔案總管的資料夾選擇對話框"""
        start_dir = str(self.folder.resolve()) if self.folder.is_dir() else str(get_default_folder())
        path_str = QFileDialog.getExistingDirectory(
            self,
            "選擇要檢視的資料夾",
            start_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if path_str:
            self.folder = Path(path_str)
            save_last_folder(self.folder)
            self.setWindowTitle(f"圖片縮圖檢視 - {self.folder}")
            self.path_edit.setText(str(self.folder.resolve()))
            self._clear_thumbnails()
            self.load_thumbnails()

    def _open_image_view(self, paths: list[Path], index: int):
        """點擊縮圖時開啟大圖檢視（左/右鍵上一張/下一張，滾輪縮放）"""
        if not paths:
            return
        dlg = ImageViewerDialog(paths, index, self)
        dlg.exec()

    def _on_thumbnail_size_changed(self, key: str):
        """縮圖尺寸選項變更時重新載入"""
        if key not in THUMBNAIL_SIZES:
            return
        self.thumbnail_size = THUMBNAIL_SIZES[key]
        save_last_thumbnail_size(key)
        self._clear_thumbnails()
        self.load_thumbnails()

    def _clear_thumbnails(self):
        """清空縮圖區域"""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_thumbnails(self):
        """載入並排列縮圖"""
        images = get_image_files(self.folder)
        if not images:
            no_files = QLabel("此資料夾內沒有找到圖片檔案。")
            no_files.setStyleSheet("color: #888; font-size: 14px;")
            self.layout.addWidget(no_files, 0, 0)
            return

        size = self.thumbnail_size
        cols = max(1, self.width() // (size + 40))
        sorted_paths = sorted(images)
        for i, path in enumerate(sorted_paths):
            row, col = divmod(i, cols)
            label = ThumbnailLabel(path, size)
            label.pathClicked.connect(lambda p, idx=i: self._open_image_view(sorted_paths, idx))
            name_label = QLabel(path.name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("color: #ccc; font-size: 11px;")
            name_label.setWordWrap(True)
            name_label.setMaximumWidth(size + 20)

            container = QWidget()
            box = QGridLayout(container)
            box.setSpacing(4)
            box.addWidget(label, 0, 0)
            box.addWidget(name_label, 1, 0)
            self.layout.addWidget(container, row, col)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow { background-color: #1e1e1e; }
        QLabel { color: #e0e0e0; }
    """)
    viewer = ImageThumbnailViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
