import re

opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\))|[1-5](?=\s*\()|[1-5](?=\s+[A-Za-z가-힣]))\s*(.*)')

lines = [
    "1 (A) which — (B) where",
    "2 (A) where — (B) who",
    "3 (A) who — (B) that",
    "4 (A) when — (B) which",
    "1. 사과",
    "2) 바나나",
    "(3) 수박",
    "① 포도",
    "이건 그냥 텍스트",
    "1"
]

for l in lines:
    m = opt_start_re.match(l)
    print(f"'{l}' ->", (m.groups() if m else None))

