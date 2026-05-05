#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FalixNodes 自动续期脚本 - 增强容错版
集成 CF 验证、GitHub Secrets 变量、TG 通知及弹窗强制穿透逻辑
"""

import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 从环境变量读取 GitHub Secrets 配置 ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")
PROXY_SOCKS5 = os.environ.get("PROXY_SOCKS5")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 时区配置
CN_TZ = timezone(timedelta(hours=8))

def cn_now() -> datetime: 
    return datetime.now(CN_TZ)

def cn_time_str() -> str: 
    return cn_now().strftime("%Y-%m-%d %H:%M:%S")

def shot(name: str) -> str: 
    return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

def notify(ok: bool, stage: str, msg: str = "", img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[WARN] TG 配置缺失，跳过通知")
        return
    try:
        text = f"🔔 FalixNodes: {'✅' if ok else '❌'} {stage}\n{msg}\n⏰ {cn_time_str()}"
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", 
                              data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except Exception as e:
        print(f"[ERROR] 通知发送失败: {e}")

def handle_turnstile(sb):
    """处理 Cloudflare Turnstile 验证"""
    try:
        time.sleep(3)
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: return True
        print("[INFO] 检测到 Turnstile，尝试验证...")
        sb.uc_gui_click_captcha()
        time.sleep(6)
        return True
    except: return False

def main():
    if not SERVER_IP:
        print("[ERROR] 未发现 FALIX_SERVER_IP 变量，请检查 GitHub Secrets 配置")
        sys.exit(1)

    # 启动虚拟显示 (Linux 环境)
    display = None
    if platform.system().lower() == "linux" and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(1920, 1080))
            display.start()
            print("[INFO] 虚拟显示已启动")
        except Exception as e:
            print(f"[ERROR] 虚拟显示启动失败: {e}")

    opts = {
        "uc": True,
        "test": True,
        "locale": "zh",
        "headed": False,
        "incognito": True,
        "timeout_multiplier": 1.5  # 整体放慢节奏，适应服务器环境
    }
    if PROXY_SOCKS5: opts["proxy"] = PROXY_SOCKS5

    try:
        with SB(**opts) as sb:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 开始续期任务，目标 IP: {SERVER_IP}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=8.0)
            
            # --- 第一阶段：通过 CF 验证 ---
            success_cf = False
            for i in range(1, 4):
                handle_turnstile(sb)
                try:
                    sb.wait_for_element_present("#IP", timeout=12)
                    success_cf = True
                    break
                except:
                    print(f"[WARN] 尝试 {i}: 验证未完成，刷新页面...")
                    sb.refresh()
                    time.sleep(5)
            
            if not success_cf:
                p = shot("cf_failed")
                sb.save_screenshot(p)
                notify(False, "验证失败", "Cloudflare 验证多次尝试未通过", p)
                return

            # --- 第二阶段：填写并点击启动 ---
            print(f"[INFO] 正在填写 IP...")
            sb.type("#IP", SERVER_IP)
            time.sleep(1)
            
            print(f"[INFO] 点击第一个启动按钮...")
            btn_1 = 'button.btn-start'
            sb.scroll_to(btn_1) # 滚动到可见区域
            sb.click(btn_1)
            
            # --- 第三阶段：处理弹窗按钮 ---
            print(f"[INFO] 等待弹窗确认按钮出现...")
            time.sleep(5) # 强制给弹窗一点加载时间
            
            success_btn2 = False
            # 尝试多种选择器和点击方式
            try:
                # 增加等待时间到 25 秒
                sb.wait_for_element_visible("#watchAdBtn", timeout=25)
                # 使用 JS 强制点击，防止被透明层、广告或其他元素遮挡
                sb.execute_script('document.getElementById("watchAdBtn").click();')
                success_btn2 = True
                print("[INFO] 已通过 JS 触发确认按钮点击")
            except:
                # 备选方案：通过 XPath 文本匹配
                try:
                    xpath_btn = "//button[contains(., '启动')]"
                    if sb.is_element_visible(xpath_btn):
                        sb.click(xpath_btn)
                        success_btn2 = True
                        print("[INFO] 已通过 XPath 触发确认按钮点击")
                except:
                    pass

            if success_btn2:
                print("✅ 续期指令已成功发送")
                time.sleep(8) # 等待几秒确认页面状态
                p = shot("success")
                sb.save_screenshot(p)
                notify(True, "续期成功", f"服务器 {SERVER_IP} 启动指令已成功下达", p)
            else:
                print("❌ 弹窗按钮超时未见")
                p = shot("popup_failed")
                sb.save_screenshot(p)
                notify(False, "弹窗失败", "第一步点击后，未在 25s 内检测到确认启动按钮", p)

    except Exception as e:
        print(f"[FATAL] 脚本崩溃: {e}")
        notify(False, "脚本崩溃", str(e))
    finally:
        if display: display.stop()
        print("[INFO] 脚本运行结束")
        os._exit(0)

if __name__ == "__main__":
    # 5分钟强制看门狗
    threading.Timer(300, lambda: os._exit(0)).start()
    main()
