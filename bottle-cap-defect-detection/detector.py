from pathlib import Path

import cv2
import streamlit as st
from ultralytics import YOLO

# 模型路径按“当前文件所在目录”解析，因此在任何工作目录下启动都能找到模型
MODEL_PATH = Path(__file__).resolve().parent / "models" / "best.pt"


@st.cache_resource
def load_model(model_file=MODEL_PATH):
    """加载 YOLO 模型。用 cache_resource 保证整个会话只加载一次。"""
    return YOLO(str(model_file))


def predict_image(img):
    """对一张 BGR 图像做缺陷检测。

    :param img: cv2 读入的 BGR 图像
    :return: (画好检测框的图像, ultralytics 的原始 results)
    """
    model = load_model()
    results = model(img)

    bbox_color = (0, 255, 0)
    text_color = (255, 0, 0)
    class_names = model.names

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            label = f"{class_names[cls]} {conf:.2f}"

            cv2.rectangle(img, (x1, y1), (x2, y2), bbox_color, 2)
            cv2.putText(
                img, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_COMPLEX, 0.6, text_color, 1, cv2.LINE_AA,
            )

    return img, results
