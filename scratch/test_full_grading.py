import sys, os, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.app_utils import parse_quiz_markdown, parse_thinking_response

raw = """문항 
1
1. 철학자 비트겐슈타인(Ludwig Wittgenstein)의 언어관을 가장 잘 설명한 문장은 무엇인가요? ① "언어는 단지 의사소통을 위한 물리적 도구에 불과하다." ② "언어의 한계가 곧 내 세계의 한계이다." ③ "인간의 언어는 유전자에 의해 완벽히 프로그래밍되어 있다." ④ "침묵은 언어의 범주에 포함되지 않는다."

✅ 정답: ②
📝 해설: 비트겐슈타인은 ...
💡 학습 팁: 비트겐슈타인 ...
🎯 평가 요소: 기억 및 이해"""

_, cleaned = parse_thinking_response(raw)
qs = parse_quiz_markdown(cleaned)
q = qs[0]

print("Answer parsed:", repr(q['answer']))
print("Options parsed:", q['options'])
print("Content:", repr(q['content']))

# Grading logic
real_ans = str(q['answer']).strip()
user_ans = "1" # WRONG answer
is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
print(f"Is wrong input (1) graded correct?: {is_correct}")
