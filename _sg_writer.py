import sys
from pathlib import Path

# The style guide content - using raw string to avoid escape issues
content = Path(sys.argv[1]).read_text(encoding='utf-8')
out = Path(r'D:\ClaudeProjects\NOLAN\projects\venezuela\style_guide.md')
out.write_text(content, encoding='utf-8')
print(f'Written {out.stat().st_size} bytes to {out}')
