import re

opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\))|[1-5](?=\s*\())?\s*(.*)')

lines = ["정답:** 2"]

for l in lines:
    m = opt_start_re.match(l)
    print(m.groups() if m else None)

