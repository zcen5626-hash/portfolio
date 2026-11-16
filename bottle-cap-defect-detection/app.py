import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase
from threading import Lock
import datetime
import cv2
from image_utils import save_image_to_file
from detector import predict_image
import data_manager
import torch
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import timedelta

st.set_page_config(
    layout='wide', 
    page_title="瓶盖缺陷检测系统", 
    page_icon="🔍",
    initial_sidebar_state="expanded"
)

torch.classes.__path__ = []
defect_manager = data_manager.DefectDataManager()

# 深色主题CSS
st.markdown("""
    <style>
    .stApp { 
        background-color: #0E1117; 
        color: #FAFAFA; 
    }
    .stButton>button { 
        background-color: #1F77B4; 
        color: white; 
        border-radius: 5px;
        padding: 0.5rem 1rem;
        border: none;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #1668A7;
    }
    .metric-box { 
        background-color: #262730; 
        border-radius: 10px; 
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        text-align: center;
        margin-bottom: 10px;
        border-left: 4px solid #1F77B4;
    }
    .metric-title { 
        font-size: 14px; 
        color: #8D99AE; 
        margin-bottom: 5px;
    }
    .metric-value { 
        font-size: 24px; 
        font-weight: bold; 
        color: #FFFFFF; 
    }
    .camera-container { 
        border-radius: 10px; 
        border: 2px solid #1F77B4;
        overflow: hidden;
    }
    .sidebar-section {
        padding: 10px 0;
        border-bottom: 1px solid #2A2F3B;
    }
    .sidebar-title {
        font-size: 18px;
        font-weight: bold;
        color: #1F77B4;
        margin-bottom: 10px;
    }
    /* 修复饼图文本颜色 */
    .stPlotlyChart, .stDataFrame, .stPyplot {
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

class LastFrameRecorder(VideoProcessorBase):
    def __init__(self):
        self.last_frame = None
        self.frame_lock = Lock()
        self.last_frame_ts = None
    
    def recv(self, frame):
        with self.frame_lock:
            self.last_frame = frame
            self.last_frame_ts = datetime.datetime.now()
        return frame

    def return_last_frame(self):
        with self.frame_lock:
            return self.last_frame
    
    def return_last_frame_ts(self):
        with self.frame_lock:
            return self.last_frame_ts

# === 侧边栏 ===
with st.sidebar:
    st.markdown('<div class="sidebar-title">控制面板</div>', unsafe_allow_html=True)
    
    # 摄像头控制
    st.markdown('### 摄像头控制')
    capture_button_status = st.button('截图', use_container_width=True)
    save_status = st.toggle('保存截图文件', value=True, key="save_toggle")
    realtime_predict_status = st.toggle('实时缺陷识别', value=False, key="predict_toggle")
    
    # 数据管理
    st.markdown('### 数据管理')
    if st.button('保存数据到CSV', use_container_width=True):
        defect_manager.save_defect_data()
        st.success('数据已保存!')
    if st.button('清除所有数据', use_container_width=True):
        defect_manager.clear_data()
        st.success('数据已清除!')
    
    # 系统信息
    st.markdown('### 系统信息')
    st.info(f"检测次数: {defect_manager.count_detections()}")
    st.info(f"检测时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 当前状态
    st.markdown('### 当前状态')
    if capture_button_status:
        st.info("已点击截图按钮")
    if save_status:
        st.info("保存截图功能已启用")
    if realtime_predict_status:
        st.info("实时识别功能已启用")

# === 主界面 ===
st.title("缺陷检测系统")

# === 第一行：摄像头 ===
st.markdown("### 实时摄像头")
st.markdown('<div class="camera-container">', unsafe_allow_html=True)
my_camera = webrtc_streamer(
    key='my_camera',
    video_processor_factory=LastFrameRecorder,
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True
)
st.markdown('</div>', unsafe_allow_html=True)

# 处理截图逻辑
if capture_button_status and my_camera and my_camera.video_processor:
    img = my_camera.video_processor.return_last_frame()
    if img:
        img = img.to_ndarray(format='rgb24')
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        ts = my_camera.video_processor.return_last_frame_ts()
        
        if save_status:
            save_image_to_file(img_bgr, ts)
            st.sidebar.success(f"截图已保存: {ts.strftime('%Y-%m-%d-%H-%M-%S')}orig.jpg")
        
        if realtime_predict_status:
            img_bgr, detections = predict_image(img_bgr)
            if detections:
                defect_manager.add_defect_data(ts, detections)
                st.sidebar.success(f"检测到 {len(detections)} 个缺陷")
        
        st.markdown("### 截图预览")
        st.image(img_bgr, channels="BGR", caption="处理后的图像")

# === 第二行：数据统计和图表 ===
st.markdown("---")
st.markdown("### 缺陷统计")

# 统计指标
cols = st.columns(5)
metrics = [
    ("检测次数", defect_manager.count_detections()),
    ("瓶盖数量", defect_manager.count_cap()),
    ("缺陷总数", defect_manager.count_all_defects()),
    ("污渍数量", defect_manager.count_dirt_defects()),
    ("划痕数量", defect_manager.count_scratch_defects())
]

for col, (title, value) in zip(cols, metrics):
    with col:
        st.markdown(f"""
            <div class="metric-box">
                <div class="metric-title">{title}</div>
                <div class="metric-value">{value}</div>
            </div>
        """, unsafe_allow_html=True)

# 图表
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("#### 缺陷类型分布")
    defect_types = ['cap', 'dirt', 'scratch']
    defect_counts = [
        defect_manager.count_cap(),
        defect_manager.count_dirt_defects(),
        defect_manager.count_scratch_defects()
    ]
    
    if sum(defect_counts) > 0:
        # 使用Plotly绘制饼图
        fig = px.pie(
            names=defect_types,
            values=defect_counts,
            title='缺陷类型分布',
            color_discrete_sequence=['#2CA02C', '#1F77B4', '#FF7F0E']
        )
        
        # 设置深色主题
        fig.update_layout(
            plot_bgcolor='rgba(14, 17, 23, 0.9)',
            paper_bgcolor='rgba(14, 17, 23, 0.9)',
            font_color='white',
            legend_font_color='white',
            title_font_color='white',
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无数据，无法生成饼图")

with chart_col2:
    st.markdown("#### 缺陷数量对比")
    if sum(defect_counts) > 0:
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = ['#1F77B4', '#FF7F0E', '#2CA02C']
        
        bars = ax.bar(defect_types, defect_counts, color=colors)
        ax.set_facecolor('#0E1117')
        fig.patch.set_facecolor('#0E1117')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        ax.title.set_color('white')
        
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', 
                        va='bottom',
                        color='white')
        
        ax.set_title('total', fontsize=16)
        ax.set_xlabel('types', fontsize=12)
        ax.set_ylabel('numbers', fontsize=12)
        ax.grid(axis='y', linestyle='--', alpha=0.3)
        
        st.pyplot(fig)
    else:
        st.info("暂无数据，无法生成柱状图")

# === 第三行：时间分组统计 ===
st.markdown("---")
st.markdown("#### 时间分组缺陷统计")

time_col, chart_col = st.columns([1, 3])

with time_col:
    # 时间范围选择
    time_range = st.selectbox(
        "统计时间段", 
        ["最近30分钟", "最近1小时", "最近3小时", "最近12小时", "最近24小时"],
        index=0
    )
    
    # 分组频率选择
    group_freq = st.selectbox(
        "分组频率",
        ["1分钟", "5分钟", "10分钟", "30分钟", "1小时"],
        index=1
    )
    
    # 缺陷类型选择
    defect_type = st.selectbox(
        "缺陷类型",
        ["污渍", "划痕", "瓶盖"],
        index=0
    )
    
    # 映射关系
    type_mapping = {"污渍": "dirt", "划痕": "scratch", "瓶盖": "cap"}
    freq_mapping = {"1分钟": "1min", "5分钟": "5min", "10分钟": "10min", "30分钟": "30min", "1小时": "1H"}
    time_mapping = {
        "最近30分钟": 30, "最近1小时": 60, "最近3小时": 180, 
        "最近12小时": 720, "最近24小时": 1440
    }

with chart_col:
    # 计算时间范围
    end_time = datetime.datetime.now()
    start_time = end_time - timedelta(minutes=time_mapping[time_range])
    
    # 获取统计数据
    counts_series = defect_manager.get_defect_counts_in_time_range(
        begin_timestamp=start_time,
        end_timestamp=end_time,
        groupby_freq=freq_mapping[group_freq],
        defect_type=type_mapping[defect_type]
    )
    
    if counts_series.empty:
        st.info("该时间段内没有缺陷数据")
    else:
        counts_df = counts_series.reset_index()
        counts_df.columns = ['时间段', '缺陷数量']
        
        # 创建柱状图
        fig = px.bar(
            counts_df,
            x='时间段',
            y='缺陷数量',
            title=f'每{group_freq}{defect_type}缺陷数量统计',
            labels={'时间段': '时间段', '缺陷数量': '缺陷数量'},
            color_discrete_sequence=['#1F77B4']
        )
        
        # 图表布局
        fig.update_layout(
            plot_bgcolor='rgba(14, 17, 23, 0.9)',
            paper_bgcolor='rgba(14, 17, 23, 0.9)',
            font_color='white',
            xaxis_title='types',
            yaxis_title='numbers',
            xaxis=dict(tickangle=45),
            margin=dict(l=20, r=20, t=60, b=40)
        )
        
        fig.update_traces(texttemplate='%{y}', textposition='outside', textfont_size=12)
        st.plotly_chart(fig, use_container_width=True)

# === 第四行：数据表格 ===
st.markdown("---")
st.markdown("#### 缺陷数据详情")
if not defect_manager.defect_data.empty:
    st.dataframe(defect_manager.defect_data, use_container_width=True)
else:
    st.info("暂无缺陷数据")