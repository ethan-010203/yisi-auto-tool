"""测试脚本 - 等待5秒后输出成功信息"""
import time
import sys

print("[TEST] 测试任务启动...", flush=True)
print("[TEST] 等待1分钟...", flush=True)

# 模拟长时间运行的任务
for i in range(60):
    time.sleep(1)
    print(f"[TEST] 已等待 {i + 1} 秒...", flush=True)

print("[TEST] 任务执行完成！")
print("[TEST] 输出: 测试成功")
sys.exit(0)
