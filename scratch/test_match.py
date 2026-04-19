import re

q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)

line = "1. 철학자 비트겐슈타인(Ludwig Wittgenstein)의 언어관을 가장 잘 설명한 문장은 무엇인가요?"
m = q_start_re.match(line)
if m:
    print("MATCH!")
else:
    print("NO MATCH!")
