import re

q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\d+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)

line = "**문항 1.** 블라블라"
m = q_start_re.match(line)
if m:
    print("MATCH!")
else:
    print("NO MATCH!")
