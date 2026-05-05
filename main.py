#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FalixNodes 自动续期脚本 - 终极修复版
新增：处理欧盟 GDPR 隐私询问弹窗
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
                              data={"chat_id": chat}, files={"photo": f}, timeout=15)
    except: pass

def handle_privacy_modal(sb):
    """处理欧盟隐私询问弹窗 (GDPR)"""
    try:
        # 常见选择器：按钮文本通常包含 "Accept all"
        selectors = [
            "button.fc-cta-consent", 
            "button:contains('Accept all')", 
            ".fc-consent-root .fc-primary-button"
        ]
        time.sleep(2)
        for selector in selectors:
            if sb.is_element_visible(selector):
                print(f"[INFO] 检测到隐私询问弹窗，正在点击同意...")
                sb.click(selector)
                time.sleep(2)
                return True
    except:
        pass
    return False

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
        print("[ERROR] 未发现 FALIX_SERVER_IP 变量")
        sys.exit(1)

    display = None
    if platform.system().lower() == "linux" and not os.environ.get("DISPLAY"):
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    opts = {
        "uc": True,
        "test": True,
        "locale": "en", # 欧洲 IP 建议用英文环境减少冲突
        "headed": False,
        "incognito": True,
        "timeout_multiplier": 1.5
    }
    if PROXY_SOCKS5: opts["proxy"] = PROXY_SOCKS5

    try:
        with SB(**opts) as sb:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 开始任务: {SERVER_IP}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=8.0)
            
            # --- 增加：处理隐私弹窗 ---
            handle_privacy_modal(sb)
            
            # --- 第一阶段：通过 CF 验证 ---
            success_cf = False
            for i in range(1, 4):
                handle_turnstile(sb)
                try:
                    # 如果 IP 输入框出现了，说明通过了
                    sb.wait_for_element_present("#IP", timeout=12)
                    success_cf = True
                    break
                except:
                    print(f"[WARN] 尝试 {i}: 页面未就绪，刷新并重试隐私处理...")
                    sb.refresh()
                    time.sleep(3)
                    handle_privacy_modal(sb)
            
            if not success_cf:
                p = shot("stage1_failed")
                sb.save_screenshot(p)
                notify(False, "验证失败", "无法越过隐私弹窗或 CF 验证", p)
                return

            # --- 第二阶段：填写并点击启动 ---
            print(f"[INFO] 正在填写 IP...")
            sb.type("#IP", SERVER_IP)
            time.sleep(1)
            
            print(f"[INFO] 点击第一个启动按钮...")
            btn_1 = 'button.btn-start'
            sb.scroll_to(btn_1)
            sb.click(btn_1)
            
            # --- 第三阶段：处理二次确认弹窗 ---
            print(f"[INFO] 等待 watchAdBtn 确认按钮...")
            time.sleep(5)
            
            success_btn2 = False
            try:
                # 针对该特定按钮增加显式等待
                sb.wait_for_element_visible("#watchAdBtn", timeout=25)
                # 使用 JS 穿透点击，不受隐私残余遮罩影响
                sb.execute_script('document.getElementById("watchAdBtn").click();')
                success_btn2 = True
            except:
                # 尝试点击任何包含“启动”字样的按钮作为保底
                try:
                    sb.execute_script('document.querySelector("button.btn-watch").click();')
                    success_btn2 = True
                except: pass

            if success_btn2:
                print("✅ 指令发送成功")
                time.sleep(8)
                p = shot("success")
                sb.save_screenshot(p)
                notify(True, "续期成功", f"服务器 {SERVER_IP} 已启动", p)
            else:
                p = shot("popup_failed")
                sb.save_screenshot(p)
                notify(False, "确认失败", "未能点击到弹窗内的确认按钮", p)

    except Exception as e:
        print(f"[FATAL] 异常: {e}")
        notify(False, "脚本崩溃", str(e))
    finally:
        if display: display.stop()
        os._exit(0)

if __name__ == "__main__":
    threading.Timer(300, lambda: os._exit(0)).start()
    main()
