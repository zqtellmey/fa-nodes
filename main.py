#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FalixNodes 自动续期脚本 - GitHub Secrets 版
"""

import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 100% 读取 GitHub Secrets 环境配置 ---
# 注意：以下变量必须在 GitHub Repo Settings -> Secrets -> Actions 中配置
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")
# 备用：代理配置（如需使用）
PROXY_SOCKS5 = os.environ.get("PROXY_SOCKS5")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 时区处理
CN_TZ = timezone(timedelta(hours=8))

def cn_now() -> datetime: return datetime.now(CN_TZ)
def cn_time_str() -> str: return cn_now().strftime("%Y-%m-%d %H:%M:%S")
def shot(name: str) -> str: return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

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
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    opts = {
        "uc": True,
        "test": True,
        "locale": "zh",
        "headed": False,
        "incognito": True,
        "timeout_multiplier": 1.5
    }
    if PROXY_SOCKS5: opts["proxy"] = PROXY_SOCKS5

    try:
        with SB(**opts) as sb:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 正在开启续期任务: {SERVER_IP}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=8.0)
            
            success = False
            for i in range(1, 4):
                handle_turnstile(sb)
                try:
                    sb.wait_for_element_present("#IP", timeout=12)
                    success = True; break
                except:
                    print(f"[WARN] 尝试 {i}: 等待超时，正在刷新页面...")
                    sb.refresh(); time.sleep(5)
            
            if not success:
                p = shot("cf_failed")
                sb.save_screenshot(p)
                notify(False, "验证失败", "Cloudflare 验证多次尝试未通过", p)
                return

            # 填写 IP 并启动
            sb.type("#IP", SERVER_IP)
            sb.click('button.btn-start')
            print("[INFO] 已点击第一阶段启动按钮")
            
            time.sleep(3)
            # 点击弹窗按钮
            if sb.wait_for_element_visible("#watchAdBtn", timeout=15):
                sb.execute_script('document.getElementById("watchAdBtn").click();')
                time.sleep(5)
                p = shot("success")
                sb.save_screenshot(p)
                notify(True, "续期成功", f"服务器 {SERVER_IP} 已成功触发启动指令", p)
            else:
                p = shot("no_popup")
                sb.save_screenshot(p)
                notify(False, "弹窗失败", "未检测到二次确认按钮 watchAdBtn", p)

    except Exception as e:
        notify(False, "运行异常", str(e))
    finally:
        if display: display.stop()
        os._exit(0)

if __name__ == "__main__":
    threading.Timer(300, lambda: os._exit(0)).start()
    main()
