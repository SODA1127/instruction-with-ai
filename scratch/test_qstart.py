import re

q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)

lines = [
    "1) 블라블라"
]

for line in lines:
    m = q_start_re.match(line)
    if m:
        num = m.group(1) or m.group(3)
        print(f"MATCH: {num}")
    else:
        print(f"NO MATCH: {line}")
