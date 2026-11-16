import os
from pathlib import Path

import pandas as pd

# 数据文件默认放在项目内的 data/ 下，可用环境变量 DEFECT_CSV_PATH 覆盖
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = Path(os.environ.get("DEFECT_CSV_PATH", BASE_DIR / "data" / "defect_data.csv"))


class DefectDataManager:
    """负责缺陷检测记录的存取与统计。"""

    COLUMN_NAMES = ["时间", "类型", "置信度", "x1", "y1", "x2", "y2"]

    def __init__(self, csv_path=DEFAULT_CSV_PATH):
        self.csv_path = Path(csv_path)
        if self.csv_path.is_file():
            # parse_dates 保证“时间”列被解析为 datetime，时间分组统计才能用
            self.defect_data = pd.read_csv(self.csv_path, parse_dates=["时间"])
        else:
            self.defect_data = pd.DataFrame(columns=self.COLUMN_NAMES)

    def add_defect_data(self, ts, results):
        """把一次检测的所有框追加进记录并立即落盘。"""
        new_data = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                cls_name = result.names[cls]
                new_data.append([ts, cls_name, conf, x1, y1, x2, y2])

        new_dataframe = pd.DataFrame(new_data, columns=self.COLUMN_NAMES)
        self.defect_data = pd.concat([self.defect_data, new_dataframe], ignore_index=True)
        self.save_defect_data()

    def save_defect_data(self):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.defect_data.to_csv(self.csv_path, index=False)

    def clear_data(self):
        self.defect_data = pd.DataFrame(columns=self.COLUMN_NAMES)

    def count_detections(self):
        return len(self.defect_data)

    def count_cap(self):
        return len(self.defect_data[self.defect_data["类型"] == "cap"])

    def count_all_defects(self):
        return len(self.defect_data[self.defect_data["类型"] != "cap"])

    def count_dirt_defects(self):
        return len(self.defect_data[self.defect_data["类型"] == "dirt"])

    def count_scratch_defects(self):
        return len(self.defect_data[self.defect_data["类型"] == "scratch"])

    def get_defect_counts_in_time_range(self, begin_timestamp, end_timestamp,
                                        groupby_freq="5min", defect_type="dirt"):
        """按时间分组统计某类缺陷的数量。

        :param begin_timestamp: 起始时间 (datetime)
        :param end_timestamp: 结束时间 (datetime)
        :param groupby_freq: 分组频率，如 1min / 5min / 1H
        :param defect_type: 缺陷类型，cap / dirt / scratch
        :return: 分组后的 Series
        """
        if "时间" not in self.defect_data.columns:
            return pd.Series(dtype="int64")

        mask = (
            (self.defect_data["时间"] >= begin_timestamp)
            & (self.defect_data["时间"] <= end_timestamp)
            & (self.defect_data["类型"] == defect_type)
        )
        filtered_data = self.defect_data.loc[mask]

        if filtered_data.empty:
            return pd.Series(dtype="int64")

        grouped = filtered_data.groupby(pd.Grouper(key="时间", freq=groupby_freq))
        return grouped.size()


if __name__ == "__main__":
    manager = DefectDataManager()
    manager.save_defect_data()
    print(f"记录文件: {manager.csv_path}")
    print(f"当前记录数: {manager.count_detections()}")
