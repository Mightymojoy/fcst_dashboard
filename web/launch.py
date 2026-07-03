import subprocess, sys, os
script = r'e:\FCST渠道预测看板系统\web\_s.py'
proc = subprocess.Popen([sys.executable, script], shell=False, creationflags=0x08000000 if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
print(f'Server PID: {proc.pid}')
