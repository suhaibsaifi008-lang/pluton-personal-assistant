import subprocess
import os

env = os.environ.copy()
env['PYTHONPATH'] = r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton\backend'

result = subprocess.run(
    [r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton\.venv\Scripts\python.exe', '-m', 'pytest', 'backend\tests', '-q'],
    cwd=r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton',
    env=env
)
print('returncode:', result.returncode)
print('stdout:', result.stdout[-300:] if result.stdout else '')
print('stderr:', result.stderr[-300:] if result.stderr else '')