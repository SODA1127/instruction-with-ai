import re

q_start_re = re.compile(r'^\s*(?:[^\w\s]\s*)*(?:(?:문항|질문|문제|Q)\s*(\د+)[\.번\)]?\s*(.*)|(\d+)(?:번\s*\.?|\.)\s+(.*))', re.IGNORECASE)
opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')

def parse(lines):
    questions = []
    current_q = None
    quiz_started = False
    for line in lines.split('\n'):
        raw_line = line
        line = line.strip()
        if not line: continue

        q_match = q_start_re.match(line)
        opt_match = opt_start_re.match(line)

        if q_match:
            prefix_num = q_match.group(1)
            # If it lacks "문항" prefix, and matches option pattern, and we expect options -> treat as option
            if not prefix_num and quiz_started and not current_q["answer"] and not current_q["explanation"]:
                if opt_match:
                    q_match = None  # Cancel question match

        if q_match:
            num = q_match.group(1) or q_match.group(3)
            cont = q_match.group(2) or q_match.group(4) or ""
            cont = cont.strip("*#- ")
            
            quiz_started = True 
            if current_q:
                questions.append(current_q)
            current_q = {"number": num, "content": cont, "options": [], "answer": "", "explanation": "", "raw": raw_line}
            continue

        if not quiz_started or not current_q: continue

        if opt_match and not current_q["answer"] and not current_q["explanation"]:
            if opt_match.group(2).strip():
                current_q["options"].append(f"{opt_match.group(1)} {opt_match.group(2).strip()}")
                current_q["raw"] += "\n" + raw_line
                continue

        current_q["content"] += "\n" + line

    if current_q: questions.append(current_q)
    return questions

text = """문항 1. 다음을 고르세요.
1. option A
2. option B
문항 2. 질문
1. opt A
2. opt B
"""
for q in parse(text):
    print("Q:", q["number"], "opts:", q["options"])
