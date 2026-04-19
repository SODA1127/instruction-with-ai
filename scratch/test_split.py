import re

content = """① 사과 ② 바나나 ③ 딸기
- 1) 1 2) 2 3) 3
- ✅ 정답: 1)
* 2) 2번! 3) 3번!
1. 1) 2) 3)
"""

# Only split if preceded by text (not formatting characters -, *, : )
content = re.sub(r'([^\n\-\*:#])\s+([①-⑩]|\([1-5]\)|[1-5][\)\.])', r'\1\n\2', content)

print(content)
