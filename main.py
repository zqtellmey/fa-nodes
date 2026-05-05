/**
 * 终极完美版：带冷却机制的 MC 监控
 * 解决 GitHub Actions 重复触发的问题
 */

export default {
  async scheduled(event, env, ctx) {
    await this.performCheck(env);
  },

  async fetch(request, env) {
    const status = await this.performCheck(env);
    // ... HTML 保持不变 (参考之前代码) ...
    return new Response("OK"); // 简化展示，逻辑核心见下
  },

  async performCheck(env) {
    const host = 'yaho.falixsrv.me';
    const port = 29344;
    const KV = env.MONITOR_DATA; // 获取 KV 绑定

    let isOnline = false;
    let actionTaken = "无需操作";

    try {
      const socket = connect({ hostname: host, port: port });
      const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout")), 5000));
      await Promise.race([socket.opened, timeoutPromise]);
      await socket.close();
      isOnline = true;

      // 如果在线，清除掉可能的“启动中”状态
      if (KV) await KV.delete("is_starting");
      
    } catch (e) {
      isOnline = false;

      // --- 关键防抖逻辑开始 ---
      if (KV) {
        const isStarting = await KV.get("is_starting");
        if (isStarting === "true") {
          actionTaken = "⏳ 服务器正在启动中，跳过重复触发";
          console.log(actionTaken);
          return { isOnline, actionTaken };
        }
      }

      // 如果没有正在启动的标记，才调用 GitHub
      const ghSuccess = await this.triggerGitHub(env);
      
      if (ghSuccess) {
        actionTaken = "✅ 已下发启动指令";
        // 设置一个 5 分钟的冷却期（或者根据你服务器开启速度决定）
        if (KV) await KV.put("is_starting", "true", { expirationTtl: 300 }); 
      } else {
        actionTaken = "❌ GitHub 触发失败";
      }
      // --- 关键防抖逻辑结束 ---
    }

    return { isOnline, actionTaken };
  },

  async triggerGitHub(env) {
    // ... 原有的 GitHub Fetch 逻辑保持不变 ...
    return true; // 假设成功
  }
};
