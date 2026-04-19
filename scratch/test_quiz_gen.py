import sys, re
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.app_utils import parse_quiz_markdown, parse_thinking_response

raw_llm_output = r"""<think>
Thinking...
</think>
여기에 퀴즈가 있습니다.
1번째 문제입니다.
1) 1
2) 2
"""

final_text, cleaned = parse_thinking_response(raw_llm_output)
qs = parse_quiz_markdown(cleaned)
print(f"Number of questions parsed: {len(qs)}")
