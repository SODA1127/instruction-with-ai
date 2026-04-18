import re

def parse_quiz_markdown(text: str) -> list[dict]:
    lines = text.split('\n')
    questions, current_q = [], None
    q_start_re = re.compile(r'(?:[\*#\-\s]*)(?:문항\s*)?(\d+)[\.번\)]\s*(.*)', re.IGNORECASE)
    opt_start_re = re.compile(r'^\s*(?:[①-⑩]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')
    ans_re, exp_re = re.compile(r'(?:정답|답)\s*[:：]?\s*(.*)', re.IGNORECASE), re.compile(r'(?:해설)\s*[:：]?\s*(.*)', re.IGNORECASE)
    quiz_started = False
    
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line: continue
        
        if line.startswith('<') and line.endswith('>'):
            continue

        q_match = q_start_re.search(line)
        if q_match and q_match.start() < 10:
            quiz_started = True 
            if current_q: questions.append(current_q)
            current_q = {"number": q_match.group(1), "content": q_match.group(2).strip(), "options": [], "answer": "", "explanation": "", "raw": raw_line}
            continue
        if not quiz_started or not current_q: continue
        opt_match = opt_start_re.match(line)
        if opt_match:
            if opt_match.group(1).strip():
                current_q["options"].append(opt_match.group(1).strip())
                current_q["raw"] += "\n" + raw_line
                continue
        a_match = ans_re.search(line)
        if a_match and a_match.start() < 10:
            current_q["answer"] = a_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
        e_match = exp_re.search(line)
        if e_match and e_match.start() < 10:
            current_q["explanation"] = e_match.group(1).strip()
            current_q["raw"] += "\n" + raw_line
            continue
        if not current_q["options"] and not current_q["answer"] and not current_q["explanation"]:
            current_q["content"] += " " + line
        elif current_q["explanation"]:
            current_q["explanation"] += " " + line
        current_q["raw"] += "\n" + raw_line
    if current_q: questions.append(current_q)
    return questions

sample = """
문항 1. 고대 바빌로니아 수학
① 바빌로니아 
② 이집트 
- ✅ 정답: ①
- 📝 해설: 바빌로니아는 60진법
- 💡 학습팁: 외워!

문항 2. [단답형] 증명
답안 선택 (Q2)
- ✅ 정답: 서로소
- 📝 해설: 귀류법
"""
qs = parse_quiz_markdown(sample)
for q in qs:
    print(q['number'], q['options'])
