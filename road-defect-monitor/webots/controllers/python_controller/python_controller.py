#!/usr/bin/env python3

# -------------------------------
# 解决 Webots Python 库路径问题
# -------------------------------
import sys
import os

# 替换为你的 Webots 实际安装路径（根据系统调整）
WEBOTS_LIB_PATH = "/usr/local/webots/lib/controller/python"  # Linux 默认
if not os.path.exists(WEBOTS_LIB_PATH):
    # Snap 安装路径
    WEBOTS_LIB_PATH = "/snap/webots/current/usr/share/webots/lib/controller/python"

if WEBOTS_LIB_PATH not in sys.path:
    sys.path.append(WEBOTS_LIB_PATH)

# -------------------------------
# 导入 Webots 相关模块
# -------------------------------
from controller import Robot, Camera, Lidar
import math

# 初始化机器人
robot = Robot()
time_step = int(robot.getBasicTimeStep())

# ---------- 获取电机 ----------
# 四个轮子（左前、右前、左后、右后）
lf_motor = robot.getDevice("lf_wheel")
rf_motor = robot.getDevice("rf_wheel")
lr_motor = robot.getDevice("lr_wheel")
rr_motor = robot.getDevice("rr_wheel")

# 设置位置为无穷大，进入速度控制模式
for motor in (lf_motor, rf_motor, lr_motor, rr_motor):
    motor.setPosition(float('inf'))
    motor.setVelocity(0.0)

# ---------- 获取相机 ----------
# 注意：世界文件中 Camera 节点没有 name，Webots 会自动命名为 "camera"
# 如果获取失败，可以尝试使用 getDeviceByIndex 或修改 .wbt 添加 name
camera = robot.getDevice("camera")
if camera is None:
    # 尝试通过索引获取（通常在设备列表中第几个，取决于顺序）
    # 该方法不推荐，最好在 .wbt 中为相机添加 name "camera"
    print("未找到名为 'camera' 的设备，尝试使用索引...")
    for i in range(robot.getNumberOfDevices()):
        dev = robot.getDeviceByIndex(i)
        if dev.getNodeType() == Camera.NODE_CAMERA:
            camera = dev
            break

if camera is not None:
    camera.enable(time_step)          # 启用相机，时间步长设为仿真步长
    print(f"相机已启用，分辨率: {camera.getWidth()}x{camera.getHeight()}")
else:
    print("警告：未找到 Camera 设备，请检查 .wbt 文件")

# ---------- 获取激光雷达 ----------
lidar = robot.getDevice("lidar")      # 世界文件中 VelodyneVLP-16 的 name 是 "lidar"
if lidar is not None:
    # 启用激光雷达，time_step 为扫描周期（建议设为仿真步长的整数倍）
    lidar.enable(time_step)
    # 可选：开启点云数据（默认已开启）
    lidar.enablePointCloud()
    print(f"激光雷达已启用，水平分辨率: {lidar.getHorizontalResolution()}, 垂直层数: {lidar.getNumberOfLayers()}")
else:
    print("警告：未找到 Lidar 设备，请确认 .wbt 中 VelodyneVLP-16 的 name 是否为 'lidar'")

# ---------- 主循环：保持前进，同时处理传感器数据 ----------
print("小车开始前进，相机和激光雷达已开启")
while robot.step(time_step) != -1:
    # 1. 驱动小车前进（左、右轮同速）
    forward_speed = 5.0   # rad/s
    lf_motor.setVelocity(forward_speed)
    lr_motor.setVelocity(forward_speed)
    rf_motor.setVelocity(forward_speed)
    rr_motor.setVelocity(forward_speed)
    
    # 2. 处理相机数据（例如每10帧打印一次图像尺寸）
    # 实际应用中你可以在这里处理图像数据
    if camera is not None and robot.getTime() % 1.0 < time_step / 1000.0:
        # 每秒显示一次相机图像信息
        image = camera.getImage()
        if image:
            print(f"相机图像获得，尺寸: {camera.getWidth()}x{camera.getHeight()}")
    
    # 3. 处理激光雷达数据（打印点云点数）
    if lidar is not None and robot.getTime() % 0.5 < time_step / 1000.0:
        point_cloud = lidar.getPointCloud()
        if point_cloud:
            print(f"激光雷达点云大小: {len(point_cloud)} 个点")
    
    # 控制循环无需额外延时，robot.step 已经处理

# 循环结束后清理（实际上不会到达这里，除非仿真停止）