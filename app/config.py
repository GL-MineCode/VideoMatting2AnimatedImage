"""全局配置与数据类定义"""

# ---- 输出格式 ----
FORMAT_GIF = "GIF"
FORMAT_WEBP = "WEBP"
FORMAT_APNG = "APNG"
ALL_FORMATS = [FORMAT_GIF, FORMAT_WEBP, FORMAT_APNG]
FORMAT_EXT = {FORMAT_GIF: "gif", FORMAT_WEBP: "webp", FORMAT_APNG: "png"}

# ---- 缩放模式 ----
SCALE_KEEP = "保持原尺寸"
SCALE_PERCENT = "按百分比"
SCALE_WIDTH = "指定宽度"
ALL_SCALE_MODES = [SCALE_KEEP, SCALE_PERCENT, SCALE_WIDTH]

# ---- 帧率模式 ----
FPS_ORIGINAL = "原帧率"
FPS_MAX = "最大帧率"
ALL_FPS_MODES = [FPS_ORIGINAL, FPS_MAX]

from dataclasses import dataclass


@dataclass
class MattingParams:
    """单视频抠图参数"""
    bg_color: tuple = (255, 255, 255)  # 背景色 RGB
    tolerance: int = 30                 # 容差 0-255
    feather: int = 8                    # 边缘羽化宽度 0-100
    border_erase: int = 1               # 去边：最外 N 像素渐变透明(0-20)


@dataclass
class OutputConfig:
    """全局输出设置"""
    out_format: str = FORMAT_GIF
    scale_mode: str = SCALE_KEEP
    scale_value: int = 100               # 百分比(1-500) 或 目标宽度(px)
    keep_rgba: bool = True               # WEBP/APNG 是否保留透明通道
    fill_color: tuple = (255, 255, 255)  # 不保留透明时合成的背景色 RGB
    fps_mode: str = FPS_ORIGINAL
    maxfps: int = 30                     # 最大帧率：输出 fps 不超过该值
    loop: int = 0                        # 循环次数，0=无限
    output_dir: str = ""                 # 输出目录，空=各源文件所在目录
