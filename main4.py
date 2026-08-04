import os, sys, time, platform, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 配置加载 ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP") or "yaho.falixsrv.me"

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TIME_FILE = Path("time.txt")  # 运行时间记录文件

# --- 2. 工具函数 ---
def notify(ok: bool, msg: str, img_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        print(f"[DEBUG] {msg}")
        return
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "✅" if ok else "❌"
    text = f"🔔 FalixNodes: {status_icon}\n内容: {msg}\n时间: {now}"
    
    if img_path and Path(img_path).exists():
        try:
            with open(img_path, "rb") as f:
                res = requests.post(
                    f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                    data={"chat_id": TG_CHAT_ID, "caption": text},
                    files={"photo": f},
                    timeout=20
                )
                if res.status_code == 200:
                    return
                else:
                    print(f"[ERROR] TG 发送图片失败, 状态码: {res.status_code}, 响应: {res.text}")
        except Exception as e:
            print(f"[ERROR] TG 上传图片异常: {e}")
            
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        print(f"[ERROR] TG 发送纯文字失败: {e}")

# --- 去广告函数 ---
def remove_ads(sb):
    """移除覆盖在页面上的 ad_position_box 广告层"""
    try:
        ad_script = """
        var adBox = document.getElementById('ad_position_box');
        if (adBox) {
            adBox.remove();
            console.log('Removed #ad_position_box');
        }
        """
        sb.execute_script(ad_script)
    except Exception as e:
        print(f"[DEBUG] 尝试去广告时出现小忽略项: {e}")

# --- 成功标识检查函数 ---
def check_and_finish(sb, step_name: str) -> bool:
    """检查网页是否已出现成功标识，若成功则截图通知并返回 True"""
    if sb.is_element_visible('#success-alert'):
        msg = sb.get_text("#success-msg")
        p_ok = str(OUTPUT_DIR / f"success_at_{step_name}.png")
        sb.save_screenshot(p_ok)
        notify(True, f"在【{step_name}】检测到成功标识: {msg}", p_ok)
        return True
    return False

# --- 更新运行时间记录 ---
def update_last_run_time():
    """将当前时间记录写入 time.txt"""
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        with open(TIME_FILE, "w", encoding="utf-8") as f:
            f.write(now_str)
        print(f"[INFO] 运行时间已更新至 {TIME_FILE}")
    except Exception as e:
        print(f"[ERROR] 更新 {TIME_FILE} 失败: {e}")

# --- 3. 主程序逻辑 ---
def main():
    # === 5分钟运行间隔校验 ===
    if TIME_FILE.exists():
        try:
            with open(TIME_FILE, "r", encoding="utf-8") as f:
                last_time_str = f.read().strip()
            if last_time_str:
                last_time = datetime.fromisoformat(last_time_str)
                now_time = datetime.now(timezone.utc)
                diff_seconds = (now_time - last_time).total_seconds()
                
                if diff_seconds < 300:  # 5分钟 = 300秒
                    wait_remaining = int(300 - diff_seconds)
                    print(f"[INFO] 距离上一次运行仅过去 {int(diff_seconds)} 秒（不足 5 分钟），还需等待 {wait_remaining} 秒。终止本次运行。")
                    return
        except Exception as e:
            print(f"[WARNING] 读取或解析 {TIME_FILE} 失败: {e}，将直接继续运行...")

    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 任务启动，IP: {SERVER_IP}")
            
            # 步骤 1: 打开网站
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)
            time.sleep(3)
            remove_ads(sb)
            
            img_step1 = str(OUTPUT_DIR / "step1_open_url.png")
            sb.save_screenshot(img_step1)
            notify(True, "步骤 1 完成: 已打开网站", img_step1)
            
            if check_and_finish(sb, "步骤 1"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 2: 输入要启动的服务器地址
            remove_ads(sb)
            sb.wait_for_element_present("#IP", timeout=15)
            sb.type("#IP", SERVER_IP)
            print(f"[INFO] 已输入 IP: {SERVER_IP}")
            
            img_step2 = str(OUTPUT_DIR / "step2_input_ip.png")
            sb.save_screenshot(img_step2)
            notify(True, f"步骤 2 完成: 已输入 IP ({SERVER_IP})", img_step2)

            if check_and_finish(sb, "步骤 2"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 3: 针对 Turnstile iframe 进行精确的 CF 验证勾选与状态判断
            remove_ads(sb)
            print("[INFO] 正在寻找并处理 CF Turnstile iframe 验证码...")
            
            iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
            
            if sb.is_element_present(iframe_selector):
                try:
                    sb.switch_to_frame(iframe_selector)
                    time.sleep(1)
                    
                    if sb.is_element_present('input[type="checkbox"]'):
                        sb.click('input[type="checkbox"]')
                    else:
                        sb.click('body')
                        
                    print("[INFO] 已在 iframe 内触发点击，等待验证结果...")
                    
                    verified = False
                    for _ in range(10):
                        time.sleep(1)
                        page_text = sb.get_page_source()
                        if any(term in page_text for term in ["成功", "Success", "Successful"]):
                            verified = True
                            print("[INFO] CF 验证成功！已检测到成功标识 span。")
                            break
                    
                    if not verified:
                        print("[WARNING] 未在规定时间内检测到验证成功的文本标识，继续尝试主流程...")
                        
                except Exception as cf_err:
                    print(f"[ERROR] 处理 iframe 内 CF 验证时出错: {cf_err}")
                finally:
                    sb.switch_to_default_content()
            else:
                print("[INFO] 未找到特定 iframe，调用 uc_gui_click_captcha 尝试自动绕过...")
                sb.uc_gui_click_captcha()

            time.sleep(3)
            remove_ads(sb)
            img_step3 = str(OUTPUT_DIR / "step3_cf_turnstile.png")
            sb.save_screenshot(img_step3)
            notify(True, "步骤 3 完成: CF 验证处理完毕", img_step3)

            if check_and_finish(sb, "步骤 3"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 4: 点击第一个按钮 (Start Server)
            remove_ads(sb)
            sb.click('button.btn-start') 
            print("[INFO] 已点击第一个按钮 (Start Server)")
            time.sleep(3)
            
            img_step4 = str(OUTPUT_DIR / "step4_click_start_btn.png")
            sb.save_screenshot(img_step4)
            notify(True, "步骤 4 完成: 已点击第一个按钮 (Start Server)", img_step4)

            if check_and_finish(sb, "步骤 4"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 5: 点击第二个按钮 (watchAdBtn)
            remove_ads(sb)
            sb.wait_for_element_visible("#watchAdBtn", timeout=15)
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("[INFO] 已点击第二个按钮 (watchAdBtn)，广告计时开始...")
            
            img_step5 = str(OUTPUT_DIR / "step5_click_watch_ad_btn.png")
            sb.save_screenshot(img_step5)
            notify(True, "步骤 5 完成: 已点击第二个按钮 (watchAdBtn)", img_step5)

            if check_and_finish(sb, "步骤 5"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 6: 等广告看完 (模拟等待 45 秒)
            for i in range(1, 6):
                time.sleep(9)
                print(f"广告进度模拟: {i*20}%...")
                
            img_step6 = str(OUTPUT_DIR / "step6_ad_finished.png")
            sb.save_screenshot(img_step6)
            notify(True, "步骤 6 完成: 45秒广告模拟等待结束", img_step6)

            if check_and_finish(sb, "步骤 6"):
                update_last_run_time()
                if display: display.stop()
                return

            # 步骤 7: POST 这个 START 的请求
            print("[INFO] 广告模拟结束，正在发送最终 POST 请求...")
            post_script = f"""
            fetch('/startserver', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
                }},
                body: 'IP={SERVER_IP}&cf-turnstile-response=',
                credentials: 'include'
            }}).then(response => {{
                if (response.redirected) {{
                    window.location.href = response.url;
                }} else {{
                    location.reload();
                }}
            }});
            """
            sb.execute_script(post_script)
            
            # 等待刷新并做最终判定
            time.sleep(10)
            
            if not check_and_finish(sb, "步骤 7 (POST)"):
                p_fail = str(OUTPUT_DIR / "flow_fail.png")
                sb.save_screenshot(p_fail)
                notify(False, "流程执行完毕，但未见成功标识，请检查截图", p_fail)

        except Exception as e:
            p_err = str(OUTPUT_DIR / "flow_error.png")
            try: sb.save_screenshot(p_err)
            except: pass
            notify(False, f"程序运行异常: {str(e)}", p_err)
        finally:
            # 无论成功还是结束流程，只要执行了主自动化流程，均在退出前刷新 time.txt
            update_last_run_time()

    if display: display.stop()

if __name__ == "__main__":
    main()
