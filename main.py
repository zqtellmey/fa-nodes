import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 配置加载 ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- 2. 工具函数 ---
def notify(ok: bool, msg: str, img_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        print(f"[DEBUG MSG] {msg}")
        return
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "✅" if ok else "❌"
    text = f"🔔 FalixNodes 调试: {status_icon}\n内容: {msg}\n时间: {now}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img_path and Path(img_path).exists():
            with open(img_path, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except Exception as e:
        print(f"[ERROR] TG 发送失败: {e}")

def handle_turnstile(sb, step_name):
    """处理 CF 验证并截图"""
    try:
        time.sleep(2)
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: 
            print("[INFO] 当前页面未发现 CF 验证框")
            return True 
        
        print("[INFO] 检测到 CF 验证框，尝试点击...")
        sb.uc_gui_click_captcha() 
        time.sleep(5)
        
        # 截图：打完勾的样子
        p = str(OUTPUT_DIR / f"debug_{step_name}_after_cf.png")
        sb.save_screenshot(p)
        notify(True, f"步骤 {step_name}: 已尝试点击 CF 验证勾选框", p)
        return True
    except: return False

def handle_privacy_modal(sb, step_name):
    """处理隐私框并记录"""
    try:
        selectors = ["button[aria-label='Accept all']", "button.fc-cta-consent"]
        for s in selectors:
            if sb.is_element_visible(s):
                sb.click(s)
                print(f"[INFO] 已处理隐私弹窗: {s}")
                time.sleep(2)
                break
    except: pass

# --- 3. 主程序逻辑 ---
def main():
    if not SERVER_IP:
        print("Error: Missing FALIX_SERVER_IP"); sys.exit(1)

    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    # 使用简洁版配置作为基础
    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 正在开启任务，目标 IP: {SERVER_IP}")
            
            # --- 步骤 1: 刚打开网页时截图 ---
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)
            p1 = str(OUTPUT_DIR / "debug_1_opened.png")
            sb.save_screenshot(p1)
            notify(True, "1. 网页已打开，准备处理验证", p1)

            # --- 步骤 2: 验证重试逻辑 + 截图 ---
            success_loaded = False
            for attempt in range(3):
                handle_privacy_modal(sb, f"Attempt_{attempt}")
                handle_turnstile(sb, f"Attempt_{attempt}")
                try:
                    sb.wait_for_element_present("#IP", timeout=10)
                    print(f"[INFO] 验证通过 (尝试次数: {attempt + 1})")
                    success_loaded = True
                    break
                except:
                    print(f"[WARN] 尝试 {attempt + 1} 失败，刷新重试...")
                    sb.refresh()
                    time.sleep(3)

            if not success_loaded:
                p_err = str(OUTPUT_DIR / "debug_cf_failed.png")
                sb.save_screenshot(p_err)
                notify(False, "验证环节最终失败，请检查截图", p_err)
                return

            # --- 步骤 3: 填写 IP 并点击第一个按钮 ---
            sb.type("#IP", SERVER_IP)
            p2 = str(OUTPUT_DIR / "debug_2_before_click1.png")
            sb.save_screenshot(p2) # 点击前的状态
            
            sb.scroll_to('button.btn-start')
            sb.click('button.btn-start')
            print("[INFO] 第一个按钮已点击")
            
            p3 = str(OUTPUT_DIR / "debug_3_after_click1.png")
            sb.save_screenshot(p3)
            notify(True, "2. 已点击第一个按钮 (Start Server)", p3)

            # --- 步骤 4: 处理二次确认按钮 (watchAdBtn) ---
            time.sleep(5)
            handle_privacy_modal(sb, "Before_Ad")
            sb.wait_for_element_visible("#watchAdBtn", timeout=20)
            
            p4 = str(OUTPUT_DIR / "debug_4_before_click2.png")
            sb.save_screenshot(p4) # 点击第二个按钮前的样子
            
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("[INFO] 第二个按钮 (watchAdBtn) 已点击")
            
            p5 = str(OUTPUT_DIR / "debug_5_after_click2.png")
            sb.save_screenshot(p5)
            notify(True, "3. 已点击第二个按钮 (Watch Ad)，开始 40s 等待", p5)

            # --- 步骤 5: 等待广告并检测结果 ---
            for i in range(1, 5):
                time.sleep(10)
                print(f"Waiting... {i*10}s elapsed.")

            try:
                sb.driver.switch_to.window(sb.driver.window_handles[0])
            except: pass

            success_selector = '#success-alert'
            if sb.is_element_visible(success_selector):
                success_text = sb.get_text("#success-msg")
                p6 = str(OUTPUT_DIR / "debug_6_success.png")
                sb.save_screenshot(p6)
                notify(True, f"4. 最终成功: {success_text}", p6)
            else:
                p_fail = str(OUTPUT_DIR / "debug_6_fail.png")
                sb.save_screenshot(p_fail)
                notify(False, "4. 广告结束，但未发现成功提示元素", p_fail)

        except Exception as e:
            p_ex = str(OUTPUT_DIR / "debug_exception.png")
            sb.save_screenshot(p_ex)
            notify(False, f"程序异常: {str(e)}", p_ex)
            print(f"Error: {e}")

    if display: display.stop()

if __name__ == "__main__":
    main()
