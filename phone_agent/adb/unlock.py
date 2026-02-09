"""
ADB 设备解锁模块
检查设备锁屏状态并自动解锁
"""

import subprocess
import time
from typing import Optional, Tuple, Callable


def get_device_pin(device_id: str) -> Optional[str]:
    """从 PIN 管理器获取设备的 PIN"""
    try:
        from web_app.models.device_pin_manager import get_device_pin_manager
        return get_device_pin_manager().get_pin(device_id)
    except ImportError:
        return None


def get_screen_size(device_id: str) -> Tuple[int, int]:
    """获取设备屏幕尺寸（考虑屏幕方向）
    
    Returns:
        Tuple[int, int]: (width, height) 根据当前屏幕方向返回正确的宽高
        横屏模式下会交换宽高，确保坐标转换正确
    """
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        
        # 获取物理尺寸
        result = subprocess.run(
            adb_prefix + ["shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        # 解析输出，优先使用 Override size
        output = result.stdout.strip()
        width, height = 1080, 2400  # 默认值
        
        for line in output.split("\n"):
            if "Override" in line:
                size_str = line.split(":")[-1].strip()
                w, h = size_str.split("x")
                width, height = int(w), int(h)
                break
        else:
            # 如果没有 Override，使用 Physical size
            for line in output.split("\n"):
                if "Physical" in line:
                    size_str = line.split(":")[-1].strip()
                    w, h = size_str.split("x")
                    width, height = int(w), int(h)
                    break
        
        # 检测屏幕方向
        # rotation: 0=portrait, 1=landscape (90°), 2=reverse portrait, 3=landscape (270°)
        try:
            rotation_result = subprocess.run(
                adb_prefix + ["shell", "dumpsys", "display", "|", "grep", "mCurrentOrientation"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            # Try alternative method if first fails
            if "mCurrentOrientation" not in rotation_result.stdout:
                rotation_result = subprocess.run(
                    adb_prefix + ["shell", "dumpsys display | grep mCurrentOrientation"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            
            # Parse rotation value
            rotation = 0
            if "mCurrentOrientation=" in rotation_result.stdout:
                import re
                match = re.search(r'mCurrentOrientation=(\d)', rotation_result.stdout)
                if match:
                    rotation = int(match.group(1))
            
            # In landscape mode (rotation 1 or 3), swap width and height
            # wm size always returns portrait dimensions (smaller x larger)
            # but for tap coordinates, we need the current orientation's dimensions
            if rotation in (1, 3):  # Landscape
                # Ensure width > height for landscape
                if width < height:
                    width, height = height, width
                    print(f"[横屏模式] 检测到横屏方向 (rotation={rotation})，交换宽高: {width}x{height}")
            else:  # Portrait (rotation 0 or 2)
                # Ensure height > width for portrait
                if width > height:
                    width, height = height, width
                    
        except Exception as e:
            print(f"检测屏幕方向失败，使用默认方向: {e}")
        
        return width, height
        
    except Exception as e:
        print(f"获取屏幕尺寸失败: {e}")
        return 1080, 2400


def is_screen_on(device_id: str) -> bool:
    """检查屏幕是否亮着"""
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys", "power", "|", "grep", "'Display Power'"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        
        # 尝试另一种方式
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys power | grep 'Display Power'"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        
        return "state=ON" in result.stdout
        
    except Exception:
        # 如果检查失败，假设屏幕是关闭的
        return False


def is_device_locked(device_id: str) -> bool:
    """检查设备是否锁屏"""
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        
        # 方法1: 检查 mDreamingLockscreen
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys window | grep mDreamingLockscreen"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "mDreamingLockscreen=true" in result.stdout:
            return True
        
        # 方法2: 检查 mShowingLockscreen
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys window | grep mShowingLockscreen"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "mShowingLockscreen=true" in result.stdout:
            return True
        
        # 方法3: 检查 isStatusBarKeyguard
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys window | grep isStatusBarKeyguard"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "isStatusBarKeyguard=true" in result.stdout:
            return True
        
        # 方法4: 检查 KeyguardController
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys activity | grep -A 5 KeyguardController"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "mKeyguardShowing=true" in result.stdout:
            return True
            
        return False
        
    except Exception as e:
        print(f"检查锁屏状态失败: {e}")
        # 如果检查失败，尝试解锁以确保安全
        return True


def wake_screen(device_id: str) -> bool:
    """唤醒屏幕"""
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"唤醒屏幕失败: {e}")
        return False


def swipe_to_unlock(device_id: str) -> bool:
    """滑动解锁 - 双滑动确保稳定性"""
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        
        # 获取屏幕尺寸
        width, height = get_screen_size(device_id)
        
        # 计算滑动坐标
        x = width // 2
        y1 = int(height * 0.9)   # 90% 高度（底部）
        y2 = int(height * 0.17)  # 17% 高度（顶部）
        
        swipe_cmd = adb_prefix + ["shell", "input", "swipe", str(x), str(y1), str(x), str(y2), "300"]
        
        # 第一次滑动
        subprocess.run(swipe_cmd, capture_output=True, timeout=5)
        time.sleep(0.2)  # 等待滑动动画
        
        # 第二次滑动（确保稳定性）
        subprocess.run(swipe_cmd, capture_output=True, timeout=5)
        time.sleep(0.3)  # 等待动画完成
        
        return True
        
    except Exception as e:
        print(f"滑动解锁失败: {e}")
        return False


def lock_screen(device_id: str) -> bool:
    """锁定屏幕"""
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        # KEYCODE_POWER (26) 用于锁屏
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "26"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"锁屏失败: {e}")
        return False


def enter_pin(device_id: str, pin: str) -> bool:
    """输入 PIN 码"""
    if not pin:
        return False
    
    try:
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        
        # 输入 PIN
        subprocess.run(
            adb_prefix + ["shell", "input", "text", pin],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.3)
        
        # 按下确认键
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "KEYCODE_ENTER"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.5)
        return True
        
    except Exception as e:
        print(f"输入 PIN 失败: {e}")
        return False


# PIN 请求回调函数类型
PinRequestCallback = Callable[[str], Optional[str]]

# 全局 PIN 请求回调
_pin_request_callback: Optional[PinRequestCallback] = None


def set_pin_request_callback(callback: PinRequestCallback):
    """设置 PIN 请求回调函数（当需要 PIN 但没有配置时调用）"""
    global _pin_request_callback
    _pin_request_callback = callback


def request_pin_from_user(device_id: str) -> Optional[str]:
    """请求用户输入 PIN"""
    global _pin_request_callback
    if _pin_request_callback:
        return _pin_request_callback(device_id)
    return None


def unlock_device(device_id: str, pin: str = None) -> Tuple[bool, str]:
    """
    解锁设备的主函数
    
    Args:
        device_id: 设备 ID
        pin: PIN 码，如果为 None 则从配置获取
    
    Returns:
        Tuple[bool, str]: (是否成功, 状态消息)
    """
    try:
        # 1. 唤醒屏幕
        if not wake_screen(device_id):
            return False, "唤醒屏幕失败"
        
        # 2. 检查是否锁屏
        if not is_device_locked(device_id):
            return True, "设备未锁屏，无需解锁"
        
        # 3. 滑动解锁
        if not swipe_to_unlock(device_id):
            return False, "滑动解锁失败"
        
        # 等待滑动动画完成 - 增加延迟以适应慢速设备
        time.sleep(1.0)  # 从0.5s增加到1.0s
        
        # 4. 检查是否还需要 PIN
        if is_device_locked(device_id):
            # 获取 PIN
            if pin is None:
                pin = get_device_pin(device_id)
            
            # 如果没有配置 PIN，请求用户输入
            if not pin:
                pin = request_pin_from_user(device_id)
                if not pin:
                    return False, "需要 PIN 解锁但未配置，请在设备中心配置 PIN"
            
            # 需要 PIN 验证
            if not enter_pin(device_id, pin):
                return False, "输入 PIN 失败"
            
            # 等待PIN验证完成 - 增加延迟以适应慢速设备
            time.sleep(1.5)  # 从0.5s增加到1.5s
            
            # 再次检查是否解锁成功 - 添加重试逻辑
            max_retries = 3
            for retry in range(max_retries):
                if not is_device_locked(device_id):
                    return True, "设备解锁成功"
                
                # 如果还锁定，等待一下再检查（给慢速设备更多时间）
                if retry < max_retries - 1:
                    time.sleep(0.8)  # 每次重试等待0.8秒
            
            # 所有重试都失败
            return False, "PIN 验证失败，设备仍然锁定"
        
        return True, "设备解锁成功"
        
    except Exception as e:
        return False, f"解锁过程出错: {str(e)}"


def ensure_device_unlocked(device_id: str, pin: str = None) -> Tuple[bool, str]:
    """
    确保设备已解锁（任务执行前调用）
    
    Returns:
        Tuple[bool, str]: (是否成功, 状态消息)
    """
    # 先唤醒屏幕
    wake_screen(device_id)
    time.sleep(0.3)
    
    # 检查是否锁屏
    if not is_device_locked(device_id):
        return True, "设备已解锁"
    
    # 尝试解锁
    return unlock_device(device_id, pin)
