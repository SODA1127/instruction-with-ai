import re
opt_start_re = re.compile(r'^\s*(?:[\-\*]\s+)?([①-⑩]|[1-5][\)\.]|(?:\([1-5]\)))\s*(.*)')
m = opt_start_re.match("- 1) Option 1")
if m: print(f"{m.group(1)} {m.group(2)}")
