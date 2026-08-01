"""预览控件：显示抠图后的帧（棋盘格透明背景），支持点击取样"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from . import matting
from .config import MattingParams


def _np_to_qimage(rgb_np):
    """HxWx3 uint8 RGB numpy -> QImage（RGB888，需保持数组存活）"""
    h, w = rgb_np.shape[:2]
    return QImage(rgb_np.data, w, h, 3 * w, QImage.Format.Format_RGB888)


class PreviewWidget(QWidget):
    colorSampled = pyqtSignal(tuple)  # 点击取样 -> (r, g, b)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_rgb = None          # 原始 RGB 帧
        self.params = MattingParams()
        self._preview_np = None        # 保持 numpy 缓冲存活
        self._qimage_ref = None        # 保持 QImage 引用
        self._pixmap = None
        self._scaled = None
        self._offset = (0, 0)
        self.setMinimumSize(360, 280)

    # ----------------------------------------------------------- 对外接口
    def set_frame(self, frame_rgb):
        self.frame_rgb = frame_rgb
        self._update()

    def set_params(self, params):
        self.params = params
        self._update()

    def has_frame(self):
        return self.frame_rgb is not None

    # ----------------------------------------------------------- 内部
    def _update(self):
        if self.frame_rgb is None:
            self._preview_np = None
            self._qimage_ref = None
            self._pixmap = None
            self._scaled = None
        else:
            rgba = matting.apply_matting(self.frame_rgb, self.params)
            self._preview_np = matting.composite_over_checker(rgba)
            self._qimage_ref = _np_to_qimage(self._preview_np)
            self._pixmap = QPixmap.fromImage(self._qimage_ref)
        self._relayout()
        self.update()

    def _relayout(self):
        if self._pixmap is None:
            self._scaled = None
            self._offset = (0, 0)
            return
        scaled = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._scaled = scaled
        self._offset = ((self.width() - scaled.width()) // 2,
                        (self.height() - scaled.height()) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        if self._scaled is not None:
            ox, oy = self._offset
            painter.drawPixmap(ox, oy, self._scaled)
        else:
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "选中左侧视频以预览抠图效果")
        painter.end()

    def mousePressEvent(self, e):
        if self.frame_rgb is None or self._scaled is None:
            return
        x = e.position().x()
        y = e.position().y()
        ox, oy = self._offset
        px, py = int(x - ox), int(y - oy)
        sw, sh = self._scaled.width(), self._scaled.height()
        if 0 <= px < sw and 0 <= py < sh:
            ih, iw = self.frame_rgb.shape[:2]
            sx = px * iw // sw
            sy = py * ih // sh
            self.colorSampled.emit(matting.sample_color(self.frame_rgb, sx, sy))
