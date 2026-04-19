import re

def clean_output(content: str) -> str:
    content = re.sub(r'([^\n\-\*:#])\s+([①-⑩]|\([1-5]\)|[1-5][\)\.])', r'\1\n\2', content)
    content = re.sub(r'(문항|문제|질문|Q)\n\s*(\d+)', r'\1 \2', content)
    return content

text = """**문항 1. 👨‍🎓 수강생 여러분, 안녕하세요! 중간고사 준비를 위해 한국어와 영어의 어순 차이, 관계대명사/관계부사, 그리고 능동태/수동태 개념을 꼼꼼히 복습해 보겠습니다.

📝 중간고사 대비 문법 및 작문 평가 문항 (5문항)

문항 1. [선택형 - 4지선다] 다음 한국어 문장을 영어로 가장 바르게 옮긴 것을 고르세요.
"나는 해외 시장을 관리하는 직원을 만났다."
1. I met an employee which manages overseas markets. 2. I met an employee who manages overseas markets. 3. I met an employee where manages overseas markets. 4. I met an employee when manages overseas markets.
"""

print(clean_output(text))
