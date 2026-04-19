import re

raw = """문항 
1
1. 철학자 비트겐슈타인

✅ 정답: ②
📝 해설: 비트겐슈타인은 ...
💡 학습 팁: 비트겐슈타인 ...
🎯 평가 요소: 기억 및 이해

문제 2
2. 다음 중 ...
"""

def repl_details(match):
    inner = match.group(1).strip()
    return f'\n\n<details>\n<summary>💡 정답 및 해설 확인하기</summary>\n<div markdown="1">\n\n{inner}\n\n</div>\n</details>\n\n'

lookahead = r'(?=\n\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q\.?|Quiz)\s*\d+[\.번\)]?|###|#|\d+(?:번\s*\.?|\.|\)))\s*|$)'
pattern = r'\n\s*(?:[^\w\s]\s*)*((?:정답|답|해설)\s*[:：]?\s*[\s\S]*?)' + lookahead
content = re.sub(pattern, repl_details, raw, flags=re.IGNORECASE)
print(content)
