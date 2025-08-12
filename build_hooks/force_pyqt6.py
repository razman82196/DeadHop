# Ensure third-party libraries that probe Qt bindings pick PyQt6
import os

os.environ.setdefault("QT_API", "pyqt6")
