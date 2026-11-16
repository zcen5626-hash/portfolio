#!/usr/bin/env python3
"""Road Defect Monitor —— Web 端最小后端。

数据来源有两种模式：

1. 真实模式（默认）
   读取检测节点写出的状态文件和最新一帧：
       data/state.json   {"ts": 1785..., "seq": 10543,
                          "counts": {"crack": 14, "pothole": 4},
                          "events": [{"id": 20, "class_name": "crack", "conf": 0.335}],
                          "frame_source": "annotated"}
       data/latest.jpg   标注后的画面

2. 演示模式（--mock）
   不依赖 ROS 和 YOLO，自己造数据，用于前端联调、录屏和截图。

接口：
    GET /            主面板 index.html
    GET /check       前端自检页
    GET /api/status  当前状态 JSON
    GET /latest.jpg  最新一帧

用法：
    python server.py                 # 真实模式，端口 8000
    python server.py --mock          # 演示模式
    python server.py --port 8080
"""

import argparse
import io
import json
import random
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
FRAME_FILE = DATA_DIR / "latest.jpg"

# 超过这个秒数没更新就算延迟 / 断线，与前端 500ms 轮询配合
LIVE_SECONDS = 3.0
STALE_SECONDS = 10.0
MAX_EVENTS = 100

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
# 状态读取
# --------------------------------------------------------------------------- #
class FileSource:
    """真实模式：读检测节点落盘的状态。"""

    def __init__(self, state_file=STATE_FILE, frame_file=FRAME_FILE):
        self.state_file = Path(state_file)
        self.frame_file = Path(frame_file)

    def state(self):
        if not self.state_file.is_file():
            return None
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def frame(self):
        if not self.frame_file.is_file():
            return None
        return self.frame_file.read_bytes()


class MockSource:
    """演示模式：自己生成一份会持续变化的检测结果。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._seq = 10_400
        self._ts = time.time()
        self._counts = {"crack": 12, "pothole": 3}
        self._events = [
            {"id": 18, "class_name": "crack", "conf": 0.313},
            {"id": 20, "class_name": "crack", "conf": 0.335},
            {"id": 5, "class_name": "pothole", "conf": 0.313},
        ]
        self._frame = self._render()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(1.0):
            with self._lock:
                self._seq += random.randint(1, 3)
                self._ts = time.time()
                if random.random() < 0.45:
                    name = random.choice(["crack", "pothole"])
                    self._counts[name] = self._counts.get(name, 0) + 1
                    self._events.insert(0, {
                        "id": self._seq,
                        "class_name": name,
                        "conf": round(random.uniform(0.28, 0.62), 3),
                    })
                    self._events = self._events[:MAX_EVENTS]
                self._frame = self._render()

    def _render(self):
        """画一张像仿真相机输出的图，并叠加统计框，模仿 annotated_image。"""
        try:
            from PIL import Image, ImageDraw
        except ImportError:  # 没装 Pillow 就退化成一个占位像素图
            return _TINY_JPEG

        width, height = 960, 540
        horizon = int(height * 0.62)
        image = Image.new("RGB", (width, height), (92, 32, 42))
        draw = ImageDraw.Draw(image)

        # 上半部分：暗红色墙面（仿真场景里的背景墙）
        for y in range(0, horizon):
            shade = int(20 * (y / horizon))
            draw.line([(0, y), (width, y)], fill=(92 + shade, 32 + shade // 2, 42))

        # 下半部分：灰色路面，加一点噪点当作纹理
        for y in range(horizon, height):
            base = 96 + int(28 * (y - horizon) / (height - horizon))
            draw.line([(0, y), (width, y)], fill=(base, base + 2, base + 6))
        for _ in range(1500):
            x = random.randint(0, width - 1)
            y = random.randint(horizon, height - 1)
            noise = random.randint(-12, 12)
            pixel = image.getpixel((x, y))
            image.putpixel((x, y), tuple(max(0, min(255, c + noise)) for c in pixel))

        # 检测框：模拟路面缺陷
        for event in self._events[:2]:
            box_w = random.randint(180, 320)
            box_h = random.randint(28, 60)
            x1 = random.randint(40, width - box_w - 40)
            y1 = random.randint(horizon + 20, height - box_h - 20)
            draw.rectangle([x1, y1, x1 + box_w, y1 + box_h], outline=(248, 60, 60), width=2)
            draw.text((x1 + 4, y1 - 14), "%s %.2f" % (event["class_name"], event["conf"]),
                      fill=(255, 190, 190))

        # 左上角统计叠加，与实机截图一致
        draw.rectangle([16, 16, 236, 104], fill=(0, 0, 0))
        draw.text((26, 24), "Defect statistics", fill=(235, 235, 235))
        draw.text((26, 44), "pothole: %d" % self._counts.get("pothole", 0), fill=(235, 235, 235))
        draw.text((26, 62), "crack: %d" % self._counts.get("crack", 0), fill=(235, 235, 235))
        draw.text((26, 80), "active tracks: %d" % random.randint(0, 3), fill=(235, 235, 235))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
        return buffer.getvalue()

    def state(self):
        with self._lock:
            return {
                "ts": self._ts,
                "seq": self._seq,
                "counts": dict(self._counts),
                "events": list(self._events[:20]),
                "frame_source": "annotated",
            }

    def frame(self):
        with self._lock:
            return self._frame


# 1x1 白色 JPEG，用于没装 Pillow 时兜底
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb00430008060607060508070707"
    "09090807090b0c130d0c0b0b0c1911130f131c17181818171a1d25201d23241f181f2b"
    "2c25262a2d2e2e2e1f2c30322f2d302d2e2e2dffc0001108000100010301220002110103"
    "1100043f0044ffc4001f0000010501010101010100000000000000000102030405060708"
    "090a0bffc400b5100002010303020403050504040000017d010203000411051221314106"
    "13516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728"
    "292a3435363738393a434445464748494a535455565758595a636465666768696a737475"
    "767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5"
    "b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2"
    "f3f4f5f6f7f8f9faffda000c03010002110311003f00fdfeff00ffd9"
)

SOURCE = None  # 由 main() 注入


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
def _no_store(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/check")
def check():
    return send_from_directory(BASE_DIR, "check.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route("/api/status")
def api_status():
    raw = SOURCE.state() or {}
    now = time.time()
    ts = raw.get("ts")
    age = None if ts is None else max(0.0, now - float(ts))
    if age is None or age > STALE_SECONDS:
        status = "offline"
    elif age > LIVE_SECONDS:
        status = "stale"
    else:
        status = "live"

    frame = SOURCE.frame()
    payload = {
        "status": status,
        "age_seconds": age,
        "counts": raw.get("counts") or {},
        "has_frame": frame is not None,
        "seq": raw.get("seq"),
        "frame_source": raw.get("frame_source", "--"),
        "events": raw.get("events") or [],
    }
    return _no_store(jsonify(payload))


@app.route("/latest.jpg")
def latest_frame():
    frame = SOURCE.frame()
    if frame is None:
        return Response(status=404)
    return _no_store(Response(frame, mimetype="image/jpeg"))


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description="Road Defect Monitor backend")
    parser.add_argument("--mock", action="store_true", help="使用演示数据，不依赖 ROS")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    args = parser.parse_args()

    if args.mock:
        SOURCE = MockSource()
        print("[mock] 演示模式：正在生成模拟检测数据")
    else:
        data_dir = Path(args.data_dir)
        SOURCE = FileSource(data_dir / "state.json", data_dir / "latest.jpg")
        print("[file] 真实模式：读取 %s" % data_dir)

    print("打开 http://%s:%d 查看面板" % (args.host, args.port))
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
