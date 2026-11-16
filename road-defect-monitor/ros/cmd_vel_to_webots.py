#!/usr/bin/env python
"""
cmd_vel_to_webots.py
将 ROS /cmd_vel (Twist) 转换为 Webots 四轮差速驱动轮速。
修复：角速度死区、速度限幅、加速度平滑、调试日志。
"""

import rospy
from geometry_msgs.msg import Twist
from webots_ros.srv import set_float


class CmdVelToWebots:
    def __init__(self):
        self.robot_name = rospy.get_param("~robot_name", "robot")
        self.wheel_distance = rospy.get_param("~wheel_distance", 0.3)
        self.wheel_radius = rospy.get_param("~wheel_radius", 0.04)

        # ---------- 调参参数 ----------
        # 角速度死区 (rad/s)：|w| 低于此值视为 0，防止微小噪声导致无故转弯
        self.w_deadband = rospy.get_param("~w_deadband", 0.02)
        # 最大线速度 (m/s)
        self.max_linear_speed = rospy.get_param("~max_linear_speed", 1.0)
        # 最大角速度 (rad/s)
        self.max_angular_speed = rospy.get_param("~max_angular_speed", 1.5)
        # 最大轮速 (rad/s) — 电机物理极限
        self.max_wheel_speed = rospy.get_param("~max_wheel_speed", 20.0)
        # 低通滤波系数 (0~1)：越大越平滑，响应越慢
        self.smooth_factor = rospy.get_param("~smooth_factor", 0.4)
        # 是否打印诊断日志
        self.verbose = rospy.get_param("~verbose", False)

        # 上一帧的左右轮速 (rad/s)，用于平滑
        self._last_left_ang = 0.0
        self._last_right_ang = 0.0

        # 等待并调用 set_position 服务，将电机切换到速度模式
        motor_names = ["lf_wheel", "rf_wheel", "lr_wheel", "rr_wheel"]

        for motor in motor_names:
            pos_service = f"/{motor}/set_position"

            try:
                rospy.wait_for_service(pos_service, timeout=5.0)
                set_pos = rospy.ServiceProxy(pos_service, set_float)
                set_pos(float("inf"))  # 关键：切换到速度控制模式
                rospy.loginfo(f"电机 {motor} 已切换到速度控制模式")
            except Exception as e:
                rospy.logerr(f"切换电机 {motor} 失败: {e}")
                rospy.signal_shutdown("无法切换电机模式")
                return

        # 创建速度服务客户端
        self.lf = rospy.ServiceProxy("/lf_wheel/set_velocity", set_float)
        self.rf = rospy.ServiceProxy("/rf_wheel/set_velocity", set_float)
        self.lr = rospy.ServiceProxy("/lr_wheel/set_velocity", set_float)
        self.rr = rospy.ServiceProxy("/rr_wheel/set_velocity", set_float)

        # 等待速度服务就绪
        rospy.wait_for_service("/lf_wheel/set_velocity")
        rospy.wait_for_service("/rf_wheel/set_velocity")
        rospy.wait_for_service("/lr_wheel/set_velocity")
        rospy.wait_for_service("/rr_wheel/set_velocity")

        # 确保初始速度为零
        self.lf(0.0)
        self.lr(0.0)
        self.rf(0.0)
        self.rr(0.0)
        rospy.loginfo("初始速度已清零")

        self.sub = rospy.Subscriber("/cmd_vel", Twist, self.cmd_callback)
        rospy.loginfo("cmd_vel_to_webots ready")
        rospy.loginfo(
            "参数: 死区=%.3f rad/s  平滑=%.2f  最大线速度=%.1f  最大角速度=%.1f  最大轮速=%.1f",
            self.w_deadband, self.smooth_factor,
            self.max_linear_speed, self.max_angular_speed, self.max_wheel_speed,
        )

    @staticmethod
    def _apply_deadband(value, threshold):
        """死区：绝对值小于 threshold 的值归零。"""
        return 0.0 if abs(value) < threshold else value

    @staticmethod
    def _clamp(value, limit):
        """限幅到 [-limit, +limit] 范围。"""
        return max(-limit, min(limit, value))

    @staticmethod
    def _lowpass(prev, curr, alpha):
        """一阶低通滤波：out = alpha * prev + (1-alpha) * curr"""
        return alpha * prev + (1.0 - alpha) * curr

    def cmd_callback(self, twist):
        # 1. 读取并限幅 cmd_vel
        v = self._clamp(twist.linear.x, self.max_linear_speed)
        w_raw = twist.angular.z
        w = self._clamp(w_raw, self.max_angular_speed)

        # 2. 角速度死区：消除微小噪声导致的无故转弯
        w = self._apply_deadband(w, self.w_deadband)

        # 3. 差速驱动运动学：线速度 → 轮子线速度
        half_track = self.wheel_distance / 2.0
        left_linear = v - w * half_track
        right_linear = v + w * half_track

        # 4. 线速度 → 角速度 (rad/s)
        left_ang = left_linear / self.wheel_radius
        right_ang = right_linear / self.wheel_radius

        # 5. 轮速限幅
        left_ang = self._clamp(left_ang, self.max_wheel_speed)
        right_ang = self._clamp(right_ang, self.max_wheel_speed)

        # 6. 低通平滑：防止轮速突变
        left_ang = self._lowpass(self._last_left_ang, left_ang, self.smooth_factor)
        right_ang = self._lowpass(self._last_right_ang, right_ang, self.smooth_factor)

        self._last_left_ang = left_ang
        self._last_right_ang = right_ang

        # 7. 发送到电机
        try:
            self.lf(left_ang)
            self.lr(left_ang)
            self.rf(right_ang)
            self.rr(right_ang)
        except Exception as e:
            rospy.logerr_throttle(1.0, "设置轮速失败: %s", e)
            return

        # 8. 调试日志
        if self.verbose:
            rospy.loginfo(
                "cmd_vel: v=%.3f  w=%.3f(原始%.3f)  →  左轮=%.3f  右轮=%.3f",
                v, w, w_raw, left_ang, right_ang,
            )


if __name__ == "__main__":
    rospy.init_node("cmd_vel_to_webots")
    CmdVelToWebots()
    rospy.spin()