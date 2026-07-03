"""查杀占用8090端口的进程（无第三方依赖）"""
import socket, os, struct, subprocess, signal

port = 8090

# Windows上检查端口占用：用netstat辅助
try:
    output = subprocess.check_output('netstat -ano', shell=True, stderr=subprocess.STDOUT).decode('gbk', errors='replace')
    for line in output.splitlines():
        if f':{port}' in line and ('LISTENING' in line or 'ESTABLISHED' in line or 'TIME_WAIT' in line or 'CLOSE_WAIT' in line):
            parts = line.strip().split()
            pid = parts[-1]
            if pid.isdigit():
                print(f'发现占用端口{port}的进程 PID={pid}')
                subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                print('已强制终止')
                break
    else:
        print(f'未找到占用端口{port}的进程')
except Exception as e:
    print(f'错误: {e}')
    # fallback: 直接尝试绑定
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('localhost', port))
        s.close()
        print(f'端口{port}实际可用')
    except OSError:
        print(f'端口{port}仍被占用，但未能定位进程')
