import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.app_utils import parse_quiz_markdown, parse_thinking_response

raw = """문항 
1
1. 철학자 비트겐슈타인(Ludwig Wittgenstein)의 언어관을 가장 잘 설명한 문장은 무엇인가요? ① "언어는 단지 의사소통을 위한 물리적 도구에 불과하다." ② "언어의 한계가 곧 내 세계의 한계이다." ③ "인간의 언어는 유전자에 의해 완벽히 프로그래밍되어 있다." ④ "침묵은 언어의 범주에 포함되지 않는다."

✅ 정답: ②
📝 해설: 비트겐슈타인은 언어가 우리가 인식하는 세계를 결정한다고 보았습니다. 즉, 내가 표현할 수 있는 언어의 범위가 곧 내가 이해하고 사고하는 세계의 범위와 같다는 뜻입니다. (참고로 '침묵의 언어'를 언급한 학자는 에드워드 홀(Edward Hall)입니다.)
💡 학습 팁: 비트겐슈타인 = "언어의 한계 = 세계의 한계" 공식으로 기억해 두세요!
🎯 평가 요소: 기억 및 이해 (학자의 핵심 철학 이해)"""

# DO NOT RUN parse_thinking_response cleanly, suppose the text in state was ALREADY generated without correct splitting!
qs = parse_quiz_markdown(raw)

for i, q in enumerate(qs):
    print(f"--- Q{q['number']} ---")
    print(f"Content: {q['content']}")
    print(f"Options: {q['options']}")
    print(f"Answer: {q['answer']}")
    print(f"Exp: {q['explanation']}")
