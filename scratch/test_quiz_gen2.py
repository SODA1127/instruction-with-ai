import sys, re
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.app_utils import parse_thinking_response, parse_quiz_markdown

raw_llm_output = r"""<think>
Thinking...
</think>
문항 3. 16$에 해당합니다.
- , 
- 바빌로니아가 점토판/쐐기문자를 사용했습니다.
- 공리적 논리 체계를 완성한 것은 고대 그리스 수학입니다.
- 💡 학습 팁: 바빌로니아 = 60진법
- 🎯 평가 요소: 이해 (특징 구별)
- —
* 문항 2* $\vec{a} \cdot \vec{b} = (2 \times 1) + (-3 \times 4)$ 일 때?
- 1) 1
- 2) 2
- 3) 3
- ✅ 정답: 1)
- 📝 해설: 벡터의 내적은 각 성분끼리 곱한 후 더하여 스칼라 값을 얻는 연산입니다. $\vec{a} \cdot \vec{b} = (2 \times 1)$
- 💡 학습 팁: 내적 공식
"""

final_text, cleaned = parse_thinking_response(raw_llm_output)
qs = parse_quiz_markdown(cleaned)
for idx, q in enumerate(qs):
    print(f"Q{q['number']}: {q['content']}")
    print(f"Options: {q['options']}")
    print(f"Answer: '{q['answer']}'")
    print(f"Explanation: '{q['explanation']}'")
    print("-" * 20)
