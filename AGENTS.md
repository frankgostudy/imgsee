# Agent Guidelines - imgSee (Image Thumbnail Viewer)

## Project Overview
imgSee is a high-performance image thumbnail viewer built with Python and PyQt6. It provides a clean, dark-themed interface for browsing local image directories with customizable thumbnail sizes and a full-screen image viewer with zoom and navigation capabilities.

---

## Environment & Commands

### Prerequisites
- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

### Development Workflow
- **Run Application:**
  ```bash
  python image_thumbnail_viewer.py
  ```
- **Install Dependencies:**
  ```bash
  pip install -r requirements.txt
  ```

### Testing & Quality Control
*Note: Currently, there is no formal test suite. If adding tests, use the following conventions:*
- **Framework:** `pytest` (Install via `pip install pytest`)
- **Run all tests:** 
  ```bash
  pytest
  ```
- **Run a single test file:** 
  ```bash
  pytest tests/test_filename.py
  ```
- **Run a specific test case:** 
  ```bash
  pytest tests/test_filename.py::test_function_name
  ```
- **Linting:** Use `ruff` for fast linting.
  ```bash
  ruff check .
  ```
- **Type Checking:** Use `mypy` for static type analysis.
  ```bash
  mypy .
  ```

---

## Code Style & Guidelines

### 1. Imports
Group imports in the following order, with a blank line between groups:
1.  **Standard Library:** `sys`, `os`, `pathlib`, etc.
2.  **Third-party Libraries:** `PyQt6` components.
3.  **Local Modules:** Internal project files.

Sort imports alphabetically within each group. Use parentheses for long import lists from a single module to maintain clean formatting.

```python
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
)
```

### 2. Naming Conventions
- **Classes:** `PascalCase` (e.g., `ImageThumbnailViewer`, `ThumbnailLabel`).
- **Functions & Methods:** `snake_case` (e.g., `load_thumbnails`, `_apply_zoom`).
- **Variables:** `snake_case` (e.g., `current_index`, `sorted_paths`).
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `IMAGE_EXTENSIONS`, `DEFAULT_THUMBNAIL_KEY`).
- **Private/Internal Members:** Prefix with a single underscore (e.g., `self._original`, `self._dragging`).

### 3. Type Hinting
All new functions and methods **must** include type hints for all parameters and return values.
- Use `|` for Union types (e.g., `Path | None`).
- Use built-in collection types: `list[Path]`, `dict[str, int]`.

```python
def get_image_files(folder: Path) -> list[Path]:
    """Retrieve all image file paths in the given folder."""
    ...
```

### 4. Formatting & Style
- **Indentation:** Strictly 4 spaces per level.
- **Line Length:** Target 88-100 characters.
- **Quotes:** Use double quotes `"` for user-facing strings and docstrings. Use single quotes `'` for internal keys/identifiers (e.g., `settings.value('key')`) if preferred, but be consistent.
- **Docstrings:** Use Google-style or simple descriptive docstrings.

### 5. Error Handling
- **Resource Validation:** Always check if external resources (like images) loaded correctly using `pixmap.isNull()`.
- **File System:** Use `pathlib.Path` for all path manipulations. Wrap directory/file access in `try...except` where permissions or existence might be an issue.
- **Exceptions:** Never use bare `except:`. Always catch specific exceptions (e.g., `FileNotFoundError`, `PermissionError`).

### 6. Internationalization & Comments
- **Current State:** The codebase currently uses Traditional Chinese for comments and some UI labels.
- **Policy:** New comments can be in English or Traditional Chinese. Ensure high-level documentation remains clear for future maintainers.

---

## Architecture & UI Patterns

### PyQt6 Conventions
- **Layout Management:** Use `QGridLayout` for the thumbnail grid and `QVBoxLayout`/`QHBoxLayout` for structural organization. Avoid absolute positioning (`setGeometry`).
- **Signal/Slot Mechanism:** Use the modern `object.signal.connect(slot)` syntax. Define custom signals using `pyqtSignal`.
- **Styling:** Maintain the dark theme palette:
    - **Primary Background:** `#1e1e1e`
    - **Widget Background:** `#2d2d2d`
    - **Text Color:** `#e0e0e0`
    - **Accent/Highlight:** `#0d7377`
- **Performance:** For large directories, consider lazy loading or threading for thumbnail generation (currently synchronous).

### Core Components
- `ImageThumbnailViewer`: The main window handling navigation and the grid.
- `ImageViewerDialog`: Full-screen modal for detailed viewing.
- `ThumbnailLabel`: A custom widget combining the image and click interaction.

---

## Persistent Configuration
The application uses `QSettings` to persist user preferences:
- `lastFolder`: The last directory opened by the user.
- `thumbnailSize`: The preferred thumbnail size ("小", "中", "大").
- `imageViewZoom`: The zoom level for the image viewer (0 for "fit to window").

When adding new persistent settings, ensure they are handled in the utility functions at the top of `image_thumbnail_viewer.py`.

---

## Agent Instructions for Modifications

1.  **Read Before Writing:** Always read the full content of `image_thumbnail_viewer.py` before proposing changes, as it is a self-contained application.
2.  **Verify UI Changes:** When modifying the UI, ensure that widgets are properly added to layouts and that their `deleteLater()` is called if they are being replaced (see `_clear_thumbnails`).
3.  **Cross-Platform Paths:** Use `Path.resolve()` and `str(path)` appropriately to ensure compatibility across Windows and Linux/macOS.
4.  **No New Dependencies:** Do not add new libraries to `requirements.txt` without explicit user approval.
5.  **Self-Verification:** After making changes, run the application to verify that the UI remains responsive and the styling is consistent.
