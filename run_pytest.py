import subprocess
import os

env = dict(os.environ)
env['PYTHONPATH'] = r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton\backend'

result = subprocess.run(
    [r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton\.venv\Scripts\python.exe', '-m', 'pytest', 'backend/tests', '-q'],
    cwd=r'C:\Users\MOHD SUHAIB\OneDrive\文档\ChatGPT\Pluton',
    env=env,
    capture_output=True,
    text=True
)
print('returncode:', result.returncode)
print('stdout:', result.stdout)
print('stderr:', result.stderr)