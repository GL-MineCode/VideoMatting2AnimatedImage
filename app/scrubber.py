"""可拖动的帧进度条：含播放头与 clip_begin / clip_end 剪辑针

指针样式：细线贯穿轨道 + 轨道外的小三角形（尖端朝内）。
- current 针：仅上三角（轨道上方）
- clip_begin / clip_end 针：仅下三角（轨道下方），颜色不同
- 三角形区域计入拖动判定；点击上半区优先选择 current、下半区优先选择剪辑针，
  从而在指针重叠时仍可区分选择
- 轨道下方绘制以帧为单位的刻度
"""
import math

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPolygonF
from PyQt6.QtWidgets import QWidget


class FrameScrubber(QWidget):
    valueChanged = pyqtSignal(int)          # 播放头位置变化
    clipChanged = pyqtSignal(int, int)      # 剪辑范围变化 (begin, end)

    PAD = 6
    HIT_W = 14             # 指针命中区域宽度
    TRACK_TOP = 18         # 轨道顶部 y
    TRACK_H = 6            # 轨道高度
    TRI = 5.5              # 小三角形半宽
    TAB_H = 4              # 三角形底边向外延伸的矩形高度

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 0
        self._value = 0
        self._clip_begin = 0
        self._clip_end = 0    # 始终归一化为具体帧索引（含），默认=maximum
        self._drag = None     # 'play' | 'begin' | 'end' | None
        self.setMinimumHeight(50)

    def _track_center_y(self):
        return self.TRACK_TOP + self.TRACK_H // 2

    # ------------------------------------------------------- 取值/赋值
    def value(self):
        return self._value

    def clip_begin(self):
        return self._clip_begin

    def clip_end(self):
        return self._clip_end

    def set_range(self, minimum, maximum):
        self._minimum = int(minimum)
        self._maximum = int(maximum)
        self._value = max(self._minimum, min(self._value, self._maximum))
        self._clip_begin = max(self._minimum, min(self._clip_begin, self._maximum))
        if self._clip_end < 0 or self._clip_end > self._maximum:
            self._clip_end = self._maximum
        else:
            self._clip_end = max(self._clip_begin, min(self._clip_end, self._maximum))
        self.update()

    def set_value(self, value, emit=True):
        v = max(self._minimum, min(self._maximum, int(value)))
        if v != self._value:
            self._value = v
            if emit:
                self.valueChanged.emit(v)
            self.update()

    def set_clip(self, begin, end):
        """end 传 -1 表示到视频末尾"""
        self._clip_begin = max(self._minimum, min(int(begin), self._maximum))
        if end < 0 or end > self._maximum:
            self._clip_end = self._maximum
        else:
            self._clip_end = max(self._clip_begin, min(int(end), self._maximum))
        self.update()

    # ------------------------------------------------------- 坐标映射
    def _track_w(self):
        return max(1, self.width() - 2 * self.PAD)

    def _x_for(self, value):
        if self._maximum <= self._minimum:
            return self.PAD
        t = (value - self._minimum) / (self._maximum - self._minimum)
        return int(round(self.PAD + t * self._track_w()))

    def _value_for(self, x):
        if self._maximum <= self._minimum:
            return self._minimum
        t = (x - self.PAD) / self._track_w()
        t = max(0.0, min(1.0, t))
        return int(round(self._minimum + t * (self._maximum - self._minimum)))

    # ------------------------------------------------------- 命中检测
    def _hit(self, x, y):
        """根据点击位置判定目标指针。上半区优先 current，下半区优先剪辑针。"""
        if self._maximum <= self._minimum:
            return None
        xb = self._x_for(self._clip_begin)
        xe = self._x_for(self._clip_end)
        xv = self._x_for(self._value)
        center = self._track_center_y()
        near_begin = abs(x - xb) <= self.HIT_W // 2
        near_end = abs(x - xe) <= self.HIT_W // 2
        near_current = abs(x - xv) <= self.HIT_W // 2
        if y < center:
            if near_current:
                return "play"
            if near_begin:
                return "begin"
            if near_end:
                return "end"
        else:
            if near_begin:
                return "begin"
            if near_end:
                return "end"
            if near_current:
                return "play"
        return "track"

    # ------------------------------------------------------- 鼠标交互
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        x = int(e.position().x())
        y = int(e.position().y())
        hit = self._hit(x, y)
        if hit in ("begin", "end"):
            self._drag = hit
        else:
            self.set_value(self._value_for(x))
            self._drag = "play"
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        x = int(e.position().x())
        if self._drag == "play":
            self.set_value(self._value_for(x))
        elif self._drag == "begin":
            v = max(self._minimum, min(self._value_for(x), self._clip_end - 1))
            if v != self._clip_begin:
                self._clip_begin = v
                self.clipChanged.emit(self._clip_begin, self._clip_end)
                self.update()
        elif self._drag == "end":
            v = max(self._clip_begin + 1, min(self._value_for(x), self._maximum))
            if v != self._clip_end:
                self._clip_end = v
                self.clipChanged.emit(self._clip_begin, self._clip_end)
                self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None

    # ------------------------------------------------------- 绘制
    def _tick_step(self):
        """选择适中的刻度步长（1/2/5 * 10^k），控制刻度数量"""
        span = self._maximum - self._minimum
        if span <= 0:
            return 1
        raw = span / 12.0
        mag = 10 ** math.floor(math.log10(raw))
        for m in (1, 2, 5, 10):
            if raw <= m * mag:
                return int(m * mag)
        return int(10 * mag)

    def _draw_ticks(self, p):
        span = self._maximum - self._minimum
        if span <= 0:
            return
        step = self._tick_step()
        tt = self.TRACK_TOP
        th = self.TRACK_H
        y0 = tt + th + 2
        y1 = y0 + 4
        lab_y = y1 + 1
        p.setPen(QColor(150, 150, 150))
        f = p.font()
        f.setPointSize(7)
        p.setFont(f)
        for v in range(self._minimum, self._maximum + 1, step):
            x = self._x_for(v)
            p.drawLine(int(x), y0, int(x), y1)
            p.drawText(int(x) - 20, lab_y, 40, 12,
                       Qt.AlignmentFlag.AlignHCenter, str(v))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tt = self.TRACK_TOP
        th = self.TRACK_H
        track = QRectF(self.PAD, tt, self._track_w(), th)

        xb = self._x_for(self._clip_begin)
        xe = self._x_for(self._clip_end)
        xv = self._x_for(self._value)

        self._draw_ticks(p)

        # 轨道
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(205, 205, 205))
        p.drawRoundedRect(track, 3, 3)

        # 剪辑范围高亮
        if xe > xb + 1:
            p.setBrush(QColor(66, 133, 244, 70))
            p.drawRoundedRect(QRectF(xb, tt, xe - xb, th), 3, 3)

        # 已播放进度
        if xv > track.left():
            p.setBrush(QColor(66, 133, 244, 160))
            p.drawRect(QRectF(track.left(), tt, xv - track.left(), th))

        # 指针：细线 + 三角
        self._draw_current(p, xv)
        self._draw_clip(p, xb, QColor(0, 150, 136))
        self._draw_clip(p, xe, QColor(220, 80, 60))
        p.end()

    def _draw_current(self, p, x):
        """current 针：细线 + 轨道上方下指三角形 + 底边延伸矩形（淡黄色）"""
        tt = self.TRACK_TOP
        th = self.TRACK_H
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 221, 51))  # 淡黄色
        p.drawRect(QRectF(x - 1.0, tt - 1, 2, th + 2))
        tri_h = self.TRI * 1.8
        base_y = tt - 1 - tri_h
        p.drawPolygon(QPolygonF([
            QPointF(x, tt - 1),
            QPointF(x - self.TRI, base_y),
            QPointF(x + self.TRI, base_y),
        ]))
        # 三角形底边（与 x 轴平行端）向外延伸矩形，扩大抓取范围
        p.drawRect(QRectF(x - self.TRI, base_y - self.TAB_H,
                          self.TRI * 2, self.TAB_H))

    def _draw_clip(self, p, x, color):
        """clip 针：细线 + 轨道下方上指三角形 + 底边延伸矩形"""
        tt = self.TRACK_TOP
        th = self.TRACK_H
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRect(QRectF(x - 1.0, tt - 1, 2, th + 2))
        tri_h = self.TRI * 1.8
        base_y = tt + th + 1 + tri_h
        p.drawPolygon(QPolygonF([
            QPointF(x, tt + th + 1),
            QPointF(x - self.TRI, base_y),
            QPointF(x + self.TRI, base_y),
        ]))
        # 三角形底边（与 x 轴平行端）向外延伸矩形，扩大抓取范围
        p.drawRect(QRectF(x - self.TRI, base_y, self.TRI * 2, self.TAB_H))
