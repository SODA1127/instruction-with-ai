import re

q_start_re = re.compile(r'^\s*(?:[\*#\-\s]*)(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)

lines = [
    "📝 문항 1. 어쩌고",
    "Q1. 어쩌고",
    "문제 1. 어쩌고",
    "1) 다음 중",
    "1번. 다음 중"
]

for line in lines:
    m = q_start_re.search(line)
    if m:
        print(f"MATCH: {line} -> Num={m.group(1) or m.group(3)}")
    else:
        print(f"NO MATCH: {line}")
