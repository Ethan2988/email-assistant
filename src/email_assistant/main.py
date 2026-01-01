"""
Email Assistant 主入口

"""

import os
import signal
import sys
import time
from .tools import Email_tool
from .system_init import system_init, stop_run, stop_all_services
from .service import (
    get_listener_status
)
from .service.scheduler_service import scheduler_service



def signal_handler(sig, frame):
    """
    处理退出信号（SIGTERM 和 SIGINT）

    Args:
        sig: 信号类型
        frame: 当前堆栈帧
    """
    print(f"\n\n收到信号 {sig}，正在优雅关闭...")
    stop_all_services()
    print("👋 程序已安全退出，再见！")
    sys.exit(0)



def main() -> None:

    # 初始化配置
    system_init()

    # 注册信号处理器（处理 Ctrl+C 和 kill 命令）
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill 命令

    # 主线程无限循环，保持程序运行
    print("邮件助手正在运行，按 Ctrl+C 退出...")
    print("-" * 60)

    try:
        while True:
            # 定期打印状态信息
            jobs = scheduler_service.list_jobs()
            #listener_status = get_listener_status()

            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 状态:")
            print(f"  定时任务: {len(jobs)} 个")
            for job in jobs:
                print(f"    - {job['name']}: 下次运行 {job.get('next_run_time', 'N/A')}")

            # 邮件监听器正在运行中

            print(f"邮件监听器正在运行中")
            # if listener_status.get('stats'):
            #     stats = listener_status['stats']
            #     print(f"    - 已收: {stats.get('total_received', 0)} 封")
            #     print(f"    - 模式切换: {stats.get('mode_switches', 0)} 次")

            time.sleep(10)  # 每10秒打印一次状态

    except KeyboardInterrupt:
        # 停止监听器，停止调度器
        stop_run()
    except Exception as e:
        print(f"❌ 系统错误: {str(e)}")
        stop_run()




if __name__ == "__main__":
    main()
