#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FalixNodes 自动续期脚本 - TG通知集成版
集成用户提供的 CF Turnstile 验证逻辑与 Telegram 通知功能
"""

import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 全局配置 ---
TARGET_URL = "https://falixnodes.net/startserver"
SERVER_IP = "yaho.falixsrv.me"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 时区配置
CN_TZ = timezone(timedelta(hours=8))

# --- 工具函数 ---
def cn_now() -> datetime:
    return datetime.now(CN_TZ)

def cn_time_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return cn_now().strftime(fmt)

def is_linux(): return platform.system().lower() == "linux"

def setup_display():
    if is_linux() and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            d = Display(visible=False, size=(1920, 1080))
            d.start()
            print("[INFO] 虚拟显示已启动")
            return d
        except Exception as e:
            print(f"[ERROR] 虚拟显示失败: {e}"); sys.exit(1)
    return None

def shot(name: str) -> str:
    return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

# --- Telegram 通知功能 ---
def notify(ok: bool, stage: str, msg: str = "", img: str = None):
    token = os.environ.get("TG_BOT_TOKEN")
    chat = os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        print("[WARN] 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过通知")
        return
    try:
        text = f"🔔 FalixNodes: {'✅' if ok else '❌'} {stage}\n{msg}\n⏰ {cn_time_str()}"
        # 发送文字
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat, "text": text}, timeout=10)
        # 如果有截图则发送图片
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                              data={"chat_id": chat}, files={"photo": f}, timeout=15)
    except Exception as e:
        print(f"[ERROR] TG通知发送失败: {e}")

# --- 核心验证逻辑 ---
def handle_turnstile(sb):
    try:
        time.sleep(2)
        # 检测是否需要验证
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: return True
        
        print("[INFO] 检测到 Turnstile，尝试自动验证...")
        sb.uc_gui_click_captcha()
        time.sleep(5)
        return True
    except: return False

# --- 主逻辑 ---
def main():
    # 启动看门狗：5分钟强制退出
    threading.Timer(300, lambda: os._exit(0)).start()

    display = setup_display()
    last_shot = None
    task_ok = False
    
    opts = {
        "uc": True, 
        "test": True, 
        "locale": "zh", 
        "headed": False, 
        "timeout_multiplier": 0.4
    }
    # 如果有代理配置可在此加入
    if os.environ.get("PROXY_SOCKS5"):
        opts["proxy"] = os.environ.get("PROXY_SOCKS5")

    try:
        with SB(**opts) as sb:
            print(f"\n[INFO] 访问页面: {TARGET_URL}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)
            
            # 1. 验证阶段
            success_loaded = False
            for attempt in range(3):
                handle_turnstile(sb)
                try:
                    sb.wait_for_element_present("#IP", timeout=8)
                    success_loaded = True
                    break
                except:
                    print(f"[WARN] 尝试 {attempt + 1}: 验证未通过，刷新中...")
                    sb.refresh()
                    time.sleep(3)

            if not success_loaded:
                last_shot = shot("cf_failed")
                sb.save_screenshot(last_shot)
                notify(False, "验证失败", "无法通过 Cloudflare 验证页面", last_shot)
                return

            # 2. 输入 IP
            print(f"[INFO] 输入服务器地址: {SERVER_IP}")
            sb.type('//*[@id="IP"]', SERVER_IP)
            
            # 3. 点击启动按钮 1
            btn_1 = '//*[@id="main-content"]/section/form/div[1]/button'
            sb.click(btn_1)
            print("[INFO] 已点击初始启动按钮")
            time.sleep(2)

            # 4. 点击弹窗启动按钮 2
            btn_2 = "#watchAdBtn"
            # 再次检查是否有二次验证
            handle_turnstile(sb)
            
            if sb.wait_for_element_visible(btn_2, timeout=12):
                sb.click(btn_2)
                task_ok = True
                last_shot = shot("success")
                sb.save_screenshot(last_shot)
                print("✅ 续期指令发送成功")
                notify(True, "续期成功", f"服务器 {SERVER_IP} 已触发启动流程", last_shot)
            else:
                last_shot = shot("btn2_not_found")
                sb.save_screenshot(last_shot)
                notify(False, "操作失败", "未检测到弹窗启动按钮（watchAdBtn）", last_shot)

    except Exception as e:
        error_msg = f"浏览器执行异常: {str(e)}"
        print(f"[FATAL] {error_msg}")
        notify(False, "系统异常", error_msg)
    finally:
        if display: display.stop()
        print("[INFO] 脚本运行结束")
        os._exit(0)

if __name__ == "__main__":
    main()
