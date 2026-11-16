import os
from pathlib import Path

import cv2

# 截图统一存到项目内的 images/original/，不再依赖启动时的当前目录
DEFAULT_SAVE_DIR = Path(__file__).resolve().parent / "images" / "original"


def generate_file_name(ts):
    return ts.strftime("%Y-%m-%d-%H-%M-%S") + "orig.jpg"


def save_image_to_file(img, ts, save_dir=DEFAULT_SAVE_DIR):
    os.makedirs(save_dir, exist_ok=True)
    full_file_path = os.path.join(save_dir, generate_file_name(ts))
    cv2.imwrite(full_file_path, img)
    return full_file_path
