"""主窗口"""
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QSlider,
    QProgressBar,
    QAbstractItemView,
    QColorDialog,
)

from .config import (
    MattingParams,
    OutputConfig,
    ALL_FORMATS,
    FORMAT_EXT,
    FORMAT_WEBP,
    FORMAT_APNG,
    ALL_SCALE_MODES,
    SCALE_PERCENT,
    SCALE_WIDTH,
    ALL_FPS_MODES,
    FPS_MAX,
)
from .preview import PreviewWidget
from .scrubber import FrameScrubber
from .video import VideoReader, bgr_to_rgb
from .worker import BatchWorker

VIDEO_FILTER = ("视频文件 (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v *.ts)"
                ";;所有文件 (*.*)")


def _color_icon(color, w=28, h=16):
    pix = QPixmap(w, h)
    pix.fill(QColor(*color))
    return QIcon(pix)


class MainWindow(QMainWindow):
    COL_FILE, COL_COLOR, COL_TOL, COL_FEATHER, COL_BORDER, COL_STATUS = range(6)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GB/BB 视频转动态图")
        self.resize(1180, 780)

        self.row_state = []      # 每行: {src, params}
        self.current_row = -1
        self.current_reader = None
        self.current_file = None
        self.worker = None
        self.completed = 0
        self.total_jobs = 0
        self._fill = (255, 255, 255)

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(40)
        self._refresh_timer.timeout.connect(self._do_preview_refresh)

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_tick)
        self.play_interval = 40

        self._update_output_controls()

    # ----------------------------------------------------------- UI 构建
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        # 顶部按钮
        top = QHBoxLayout()
        self.btn_add = QPushButton("添加视频")
        self.btn_remove = QPushButton("移除选中")
        self.btn_clear = QPushButton("清空列表")
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_remove)
        top.addWidget(self.btn_clear)
        top.addStretch(1)
        self.btn_start = QPushButton("开始转换")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        root.addLayout(top)

        # 中间：表格 + 预览
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["视频文件", "背景色", "容差", "羽化", "去边", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self.table)

        right = QWidget()
        rv = QVBoxLayout(right)

        self.preview = PreviewWidget()
        self.preview.colorSampled.connect(self._on_color_sampled)
        rv.addWidget(self.preview, 1)

        # 帧进度条（含可拖动的剪辑针）
        sc = QHBoxLayout()
        sc.addWidget(QLabel("剪辑:"))
        self.scrubber = FrameScrubber()
        self.scrubber.valueChanged.connect(self._schedule_preview_refresh)
        self.scrubber.clipChanged.connect(self._on_clip_changed)
        sc.addWidget(self.scrubber, 1)
        rv.addLayout(sc)

        # 逐帧控制按钮
        ctrl = QHBoxLayout()
        self.btn_play = QPushButton("播放")
        self.btn_rewind = QPushButton("回退")
        self.btn_prev = QPushButton("上一帧")
        self.btn_next = QPushButton("下一帧")
        self.btn_play.clicked.connect(self._on_play)
        self.btn_rewind.clicked.connect(self._on_rewind)
        self.btn_prev.clicked.connect(self._on_prev_frame)
        self.btn_next.clicked.connect(self._on_next_frame)
        ctrl.addWidget(self.btn_play)
        ctrl.addWidget(self.btn_rewind)
        ctrl.addWidget(self.btn_prev)
        ctrl.addWidget(self.btn_next)
        ctrl.addStretch(1)
        self.frame_label = QLabel("0/0")
        ctrl.addWidget(self.frame_label)
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("color: #666;")
        ctrl.addWidget(self.total_label)
        rv.addLayout(ctrl)

        # 抠图参数面板
        mp = QGroupBox("抠图参数（应用于当前选中视频）")
        mg = QGridLayout(mp)
        mg.addWidget(QLabel("背景色:"), 0, 0)
        self.btn_bg_color = QPushButton()
        self.btn_bg_color.clicked.connect(self._on_pick_bg_color)
        mg.addWidget(self.btn_bg_color, 0, 1, 1, 2)

        mg.addWidget(QLabel("容差:"), 1, 0)
        self.sl_tol = QSlider(Qt.Orientation.Horizontal)
        self.sl_tol.setRange(0, 255)
        self.sp_tol = QSpinBox()
        self.sp_tol.setRange(0, 255)
        self.sl_tol.valueChanged.connect(self.sp_tol.setValue)
        self.sp_tol.valueChanged.connect(self._on_params_changed)
        mg.addWidget(self.sl_tol, 1, 1)
        mg.addWidget(self.sp_tol, 1, 2)

        mg.addWidget(QLabel("羽化:"), 2, 0)
        self.sl_feather = QSlider(Qt.Orientation.Horizontal)
        self.sl_feather.setRange(0, 100)
        self.sp_feather = QSpinBox()
        self.sp_feather.setRange(0, 100)
        self.sl_feather.valueChanged.connect(self.sp_feather.setValue)
        self.sp_feather.valueChanged.connect(self._on_params_changed)
        mg.addWidget(self.sl_feather, 2, 1)
        mg.addWidget(self.sp_feather, 2, 2)

        mg.addWidget(QLabel("去边:"), 3, 0)
        self.sl_border = QSlider(Qt.Orientation.Horizontal)
        self.sl_border.setRange(0, 20)
        self.sp_border = QSpinBox()
        self.sp_border.setRange(0, 20)
        self.sp_border.setValue(1)
        self.sl_border.valueChanged.connect(self.sp_border.setValue)
        self.sp_border.valueChanged.connect(self._on_params_changed)
        mg.addWidget(self.sl_border, 3, 1)
        mg.addWidget(self.sp_border, 3, 2)
        mg.addWidget(QLabel("去边=将画面最外 N 像素渐变透明，用于去除边缘残留（如顶部绿缝）"), 4, 0, 1, 3)
        rv.addWidget(mp)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # 输出设置
        op = QGroupBox("输出设置（全局）")
        og = QGridLayout(op)
        og.addWidget(QLabel("格式:"), 0, 0)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(ALL_FORMATS)
        self.cmb_format.currentTextChanged.connect(self._update_output_controls)
        og.addWidget(self.cmb_format, 0, 1)

        og.addWidget(QLabel("缩放:"), 0, 2)
        self.cmb_scale = QComboBox()
        self.cmb_scale.addItems(ALL_SCALE_MODES)
        self.cmb_scale.currentTextChanged.connect(self._update_output_controls)
        self.sp_scale = QSpinBox()
        self.sp_scale.setValue(100)
        og.addWidget(self.cmb_scale, 0, 3)
        og.addWidget(self.sp_scale, 0, 4)

        og.addWidget(QLabel("RGBA:"), 0, 5)
        self.chk_rgba = QCheckBox("保留透明通道")
        self.chk_rgba.setChecked(True)
        self.chk_rgba.toggled.connect(self._update_output_controls)
        self.btn_fill = QPushButton("填充色")
        self.btn_fill.clicked.connect(self._on_pick_fill_color)
        og.addWidget(self.chk_rgba, 0, 6)
        og.addWidget(self.btn_fill, 0, 7)

        og.addWidget(QLabel("帧率:"), 1, 0)
        self.cmb_fps = QComboBox()
        self.cmb_fps.addItems(ALL_FPS_MODES)
        self.cmb_fps.currentTextChanged.connect(self._update_output_controls)
        self.sp_maxfps = QSpinBox()
        self.sp_maxfps.setRange(1, 120)
        self.sp_maxfps.setValue(30)
        self.lbl_maxfps = QLabel("输出最大 fps")
        og.addWidget(self.cmb_fps, 1, 1)
        og.addWidget(self.sp_maxfps, 1, 2)
        og.addWidget(self.lbl_maxfps, 1, 3)

        og.addWidget(QLabel("循环次数:"), 1, 5)
        self.sp_loop = QSpinBox()
        self.sp_loop.setRange(0, 1000)
        self.sp_loop.setValue(0)
        self.lbl_loop = QLabel("(0=无限)")
        og.addWidget(self.sp_loop, 1, 6)
        og.addWidget(self.lbl_loop, 1, 7)

        og.addWidget(QLabel("输出目录:"), 2, 0)
        self.ed_dir = QLineEdit()
        self.ed_dir.setPlaceholderText("留空 = 各视频源文件所在目录")
        self.btn_dir = QPushButton("浏览...")
        self.btn_dir.clicked.connect(self._on_pick_dir)
        og.addWidget(self.ed_dir, 2, 1, 1, 6)
        og.addWidget(self.btn_dir, 2, 7)
        root.addWidget(op)

        # 底部
        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label = QLabel("就绪")
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.status_label)
        root.addLayout(bottom)

        self.setCentralWidget(central)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)

    # ----------------------------------------------------------- 文件列表
    def _on_add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", VIDEO_FILTER)
        for f in files:
            self._append_row(f)

    def _append_row(self, path):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.row_state.append({"src": path, "params": MattingParams(),
                               "clip_begin": 0, "clip_end": -1})
        self.table.setItem(row, self.COL_FILE, QTableWidgetItem(path))
        self.table.setItem(row, self.COL_COLOR,
                           QTableWidgetItem(str((255, 255, 255))))
        self.table.setItem(row, self.COL_TOL, QTableWidgetItem("30"))
        self.table.setItem(row, self.COL_FEATHER, QTableWidgetItem("8"))
        self.table.setItem(row, self.COL_BORDER, QTableWidgetItem("1"))
        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem("等待"))
        self.table.selectRow(row)

    def _on_remove(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()},
                      reverse=True)
        for r in rows:
            self.table.removeRow(r)
            del self.row_state[r]
        self._clear_preview()
        self.current_row = -1
        self._reset_progress()

    def _on_clear(self):
        self.table.setRowCount(0)
        self.row_state.clear()
        self._clear_preview()
        self.current_row = -1
        self._reset_progress()

    def _clear_preview(self):
        if self.current_reader is not None:
            self.current_reader.close()
            self.current_reader = None
        self.current_file = None
        self.preview.set_frame(None)
        self.scrubber.set_range(0, 0)
        self.frame_label.setText("0/0")
        self.total_label.setText("")

    # ----------------------------------------------------------- 预览加载
    def _on_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        self._load_row(rows[0].row())

    def _load_row(self, row):
        if not (0 <= row < len(self.row_state)):
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self._stop_playback()
        st = self.row_state[row]
        if self.current_file != st["src"]:
            reader = VideoReader(st["src"])
            if not reader.open():
                QMessageBox.warning(self, "打开失败", reader.error)
                return
            if self.current_reader is not None:
                self.current_reader.close()
            self.current_reader = reader
            self.current_file = st["src"]
            self.current_row = row
            n = max(0, reader.frame_count - 1)
            self.scrubber.set_range(0, n)
            self.play_interval = (max(16, int(round(1000.0 / reader.fps)))
                                  if reader.fps > 0 else 40)
            self._update_total_label(reader.frame_count, reader.fps)
            self.scrubber.set_clip(st.get("clip_begin", 0), st.get("clip_end", -1))
        else:
            self.current_row = row
            self.scrubber.set_clip(st.get("clip_begin", 0), st.get("clip_end", -1))

        p = st["params"]
        self._set_bg_button(p.bg_color)
        self.sl_tol.blockSignals(True)
        self.sp_tol.blockSignals(True)
        self.sl_tol.setValue(p.tolerance)
        self.sp_tol.setValue(p.tolerance)
        self.sl_tol.blockSignals(False)
        self.sp_tol.blockSignals(False)
        self.sl_feather.blockSignals(True)
        self.sp_feather.blockSignals(True)
        self.sl_feather.setValue(p.feather)
        self.sp_feather.setValue(p.feather)
        self.sl_feather.blockSignals(False)
        self.sp_feather.blockSignals(False)
        self.sl_border.blockSignals(True)
        self.sp_border.blockSignals(True)
        self.sl_border.setValue(p.border_erase)
        self.sp_border.setValue(p.border_erase)
        self.sl_border.blockSignals(False)
        self.sp_border.blockSignals(False)

        self._schedule_preview_refresh()

    def _schedule_preview_refresh(self):
        self._refresh_timer.start()

    def _do_preview_refresh(self):
        if self.current_reader is None or not (0 <= self.current_row < len(self.row_state)):
            return
        idx = self.scrubber.value()
        frame_bgr = self.current_reader.read_frame(idx)
        if frame_bgr is None:
            return
        self.preview.set_frame(bgr_to_rgb(frame_bgr))
        p = self.row_state[self.current_row]["params"]
        self.preview.set_params(p)
        total = max(0, self.current_reader.frame_count - 1)
        self.frame_label.setText(f"{idx}/{total}")

    # ----------------------------------------------------------- 播放控制
    def _on_play(self):
        if self.play_timer.isActive():
            self._stop_playback()
            return
        if self.current_reader is None:
            return
        if self.scrubber.value() >= self.scrubber.clip_end():
            self.scrubber.set_value(self.scrubber.clip_begin())
        self.btn_play.setText("暂停")
        self.play_timer.start(self.play_interval)

    def _stop_playback(self):
        self.play_timer.stop()
        self.btn_play.setText("播放")

    def _on_rewind(self):
        """回退到 clip_begin 位置"""
        self.scrubber.set_value(self.scrubber.clip_begin())
        self._do_preview_refresh()

    def _update_total_label(self, count, fps):
        if count > 0:
            if fps > 0:
                self.total_label.setText(f"原始帧数 {count} 帧 · {fps:.1f} fps")
            else:
                self.total_label.setText(f"原始帧数 {count} 帧")
        else:
            self.total_label.setText("")
    def _on_play_tick(self):
        if self.current_reader is None:
            self._stop_playback()
            return
        v = self.scrubber.value()
        if v >= self.scrubber.clip_end():
            self._stop_playback()
            return
        self.scrubber.set_value(v + 1)
        self._do_preview_refresh()

    def _on_prev_frame(self):
        self.scrubber.set_value(self.scrubber.value() - 1)
        self._do_preview_refresh()

    def _on_next_frame(self):
        self.scrubber.set_value(self.scrubber.value() + 1)
        self._do_preview_refresh()

    def _on_clip_changed(self, begin, end):
        if not (0 <= self.current_row < len(self.row_state)):
            return
        st = self.row_state[self.current_row]
        st["clip_begin"] = begin
        st["clip_end"] = end
        self.status_label.setText(f"剪辑范围: {begin} - {end}")

    # ----------------------------------------------------------- 抠图参数
    def _current_params(self):
        if 0 <= self.current_row < len(self.row_state):
            return self.row_state[self.current_row]["params"]
        return MattingParams()

    def _on_params_changed(self):
        if not (0 <= self.current_row < len(self.row_state)):
            return
        p = self.row_state[self.current_row]["params"]
        p.tolerance = self.sp_tol.value()
        p.feather = self.sp_feather.value()
        p.border_erase = self.sp_border.value()
        self.table.item(self.current_row, self.COL_TOL).setText(str(p.tolerance))
        self.table.item(self.current_row, self.COL_FEATHER).setText(str(p.feather))
        self.table.item(self.current_row, self.COL_BORDER).setText(str(p.border_erase))
        self._schedule_preview_refresh()

    def _on_pick_bg_color(self):
        color = QColorDialog.getColor(QColor(*self._current_params().bg_color),
                                      self, "选择背景色")
        if color.isValid():
            self._apply_bg_color((color.red(), color.green(), color.blue()))

    def _on_color_sampled(self, rgb):
        self._apply_bg_color(rgb)

    def _apply_bg_color(self, rgb):
        if not (0 <= self.current_row < len(self.row_state)):
            return
        p = self.row_state[self.current_row]["params"]
        p.bg_color = rgb
        self._set_bg_button(rgb)
        self.table.item(self.current_row, self.COL_COLOR).setText(str(rgb))
        self._schedule_preview_refresh()

    def _set_bg_button(self, rgb):
        self.btn_bg_color.setIcon(_color_icon(rgb))
        self.btn_bg_color.setText(f"RGB{rgb}")

    # ----------------------------------------------------------- 输出设置
    def _on_pick_fill_color(self):
        color = QColorDialog.getColor(QColor(*self._fill), self, "选择填充色")
        if color.isValid():
            self._fill = (color.red(), color.green(), color.blue())
            self._refresh_fill_button()

    def _refresh_fill_button(self):
        self.btn_fill.setIcon(_color_icon(self._fill))
        self.btn_fill.setText(f"RGB{self._fill}")

    def _on_pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ed_dir.setText(d)

    def _update_output_controls(self):
        fmt = self.cmb_format.currentText()
        is_rgba_ok = fmt in (FORMAT_WEBP, FORMAT_APNG)
        self.chk_rgba.setEnabled(is_rgba_ok)
        self.btn_fill.setEnabled(is_rgba_ok and not self.chk_rgba.isChecked())

        sm = self.cmb_scale.currentText()
        if sm == SCALE_PERCENT:
            self.sp_scale.setRange(1, 500)
            self.sp_scale.setSuffix(" %")
            if self.sp_scale.value() < 1:
                self.sp_scale.setValue(100)
        elif sm == SCALE_WIDTH:
            self.sp_scale.setRange(16, 8192)
            self.sp_scale.setSuffix(" px")
        else:
            self.sp_scale.setRange(1, 100)
            self.sp_scale.setSuffix("")

        is_maxfps = self.cmb_fps.currentText() == FPS_MAX
        self.sp_maxfps.setEnabled(is_maxfps)
        self.lbl_maxfps.setEnabled(is_maxfps)
        self._refresh_fill_button()

    def collect_output_config(self):
        return OutputConfig(
            out_format=self.cmb_format.currentText(),
            scale_mode=self.cmb_scale.currentText(),
            scale_value=self.sp_scale.value(),
            keep_rgba=self.chk_rgba.isChecked(),
            fill_color=self._fill,
            fps_mode=self.cmb_fps.currentText(),
            maxfps=self.sp_maxfps.value(),
            loop=self.sp_loop.value(),
            output_dir=self.ed_dir.text().strip(),
        )

    # ----------------------------------------------------------- 转换控制
    def _is_writable(self, d):
        """检测目录是否可写（实际创建临时文件验证，Windows 上最可靠）"""
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".gb_write_probe")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
            return True
        except OSError:
            return False

    def _fallback_output_dir(self):
        """返回一个确定可写的输出目录（桌面/视频/图片/文档下建专用文件夹）"""
        home = os.path.expanduser("~")
        for base in ("Desktop", "Videos", "Pictures", "Documents"):
            cand = os.path.join(home, base, "GB2动图输出")
            if self._is_writable(cand):
                return cand
        return None

    def _on_start(self):
        self._stop_playback()
        if not self.row_state:
            QMessageBox.information(self, "提示", "请先添加视频文件")
            return
        outcfg = self.collect_output_config()
        out_dir = outcfg.output_dir
        if out_dir:
            if not os.path.isdir(out_dir):
                QMessageBox.warning(self, "错误", "输出目录不存在")
                return
            if not self._is_writable(out_dir):
                QMessageBox.warning(
                    self, "输出目录不可写",
                    f"输出目录不可写（没有写入权限）：\n{out_dir}\n\n"
                    "请换一个可写的目录，或清空输出目录让它自动选择。")
                return

        jobs = []
        used = set()
        redirected = []          # 被自动改道输出目录的源文件
        fallback = None          # 兜底可写目录
        for i, st in enumerate(self.row_state):
            src = st["src"]
            d = out_dir or os.path.dirname(src)
            if not self._is_writable(d):
                # 目标目录不可写（如源文件位于 Program Files 等受保护目录），自动改道
                if fallback is None:
                    fallback = self._fallback_output_dir()
                if fallback is None:
                    QMessageBox.critical(self, "错误", "找不到可写的输出目录")
                    return
                d = fallback
                redirected.append(os.path.basename(src))
            stem = os.path.splitext(os.path.basename(src))[0]
            dst = os.path.join(d, f"{stem}.{FORMAT_EXT[outcfg.out_format]}")
            n = 1
            while dst in used:
                dst = os.path.join(d, f"{stem}_{n}.{FORMAT_EXT[outcfg.out_format]}")
                n += 1
            used.add(dst)
            jobs.append((i, src, dst, st["params"],
                         st.get("clip_begin", 0), st.get("clip_end", -1)))
            self.table.item(i, self.COL_STATUS).setText("等待")
            self.table.item(i, self.COL_STATUS).setForeground(QColor("black"))

        if redirected:
            QMessageBox.information(
                self, "输出目录已自动调整",
                "以下文件的源目录不可写，输出已改到：\n" + fallback + "\n\n"
                + "\n".join(f"· {f}" for f in redirected))

        self.worker = BatchWorker(jobs, outcfg)
        self.worker.video_started.connect(self._on_video_started)
        self.worker.video_progress.connect(self._on_video_progress)
        self.worker.video_finished.connect(self._on_video_finished)
        self.worker.all_finished.connect(self._on_all_finished)
        self.completed = 0
        self.total_jobs = len(jobs)
        self.progress.setRange(0, self.total_jobs)
        self.progress.setValue(0)
        self.status_label.setText(f"开始转换：{self.total_jobs} 个文件")
        self._set_running(True)
        self.worker.start()

    def _on_stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("正在停止...")

    def _on_video_started(self, row, src):
        self.table.item(row, self.COL_STATUS).setText("转换中...")
        self.table.item(row, self.COL_STATUS).setForeground(QColor("#0077cc"))
        self.table.selectRow(row)

    def _on_video_progress(self, row, cur, total):
        self.table.item(row, self.COL_STATUS).setText(f"{cur}/{total} 帧")

    def _on_video_finished(self, row, ok, msg):
        self.completed += 1
        self.progress.setValue(self.completed)
        if ok:
            self.table.item(row, self.COL_STATUS).setText("完成")
            self.table.item(row, self.COL_STATUS).setForeground(QColor("green"))
        else:
            self.table.item(row, self.COL_STATUS).setText("失败")
            self.table.item(row, self.COL_STATUS).setForeground(QColor("red"))
            fname = os.path.basename(self.row_state[row]["src"]) \
                if 0 <= row < len(self.row_state) else ""
            QMessageBox.critical(self, "转换失败", f"文件: {fname}\n\n{msg}")
        self.status_label.setText(f"进度 {self.completed}/{self.total_jobs} · {msg}")

    def _on_all_finished(self):
        self._set_running(False)
        ok_cnt = sum(
            1 for r in range(self.table.rowCount())
            if self.table.item(r, self.COL_STATUS)
            and self.table.item(r, self.COL_STATUS).text() == "完成"
        )
        self.status_label.setText(f"全部完成：成功 {ok_cnt}/{self.total_jobs}")
        QMessageBox.information(self, "完成",
                                f"转换完成：共 {self.total_jobs} 个，成功 {ok_cnt} 个")

    def _set_running(self, running):
        for btn in (self.btn_start, self.btn_stop, self.btn_add,
                    self.btn_remove, self.btn_clear):
            btn.setEnabled(not running if btn is not self.btn_stop else running)

    def _reset_progress(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label.setText("就绪")

    def closeEvent(self, e):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)
        super().closeEvent(e)
