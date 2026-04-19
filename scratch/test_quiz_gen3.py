import sys, re
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.app_utils import parse_thinking_response, parse_quiz_markdown

raw_llm_output = r"""<think>
Thinking...
</think>
1. 문항입니다
1) 옵션 1 2) 옵션 2 3) 옵션 3
정답: 2)
해설: 2번이 맞습니다.
"""

final_text, cleaned = parse_thinking_response(raw_llm_output)
qs = parse_quiz_markdown(cleaned)
for idx, q in enumerate(qs):
    print(f"Q{q['number']}: {q['content']}")
    print(f"Options: {q['options']}")
    print(f"Answer: '{q['answer']}'")
    print(f"Explanation: '{q['explanation']}'")
    print("-" * 20)
