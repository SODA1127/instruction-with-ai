import re

content = "1) hello $2 \\times 1)$ and 2) world $3 \\times 2)$ 3) test"

# Find all math blocks
placeholders = {}
def repl_math(m):
    key = f"__MATH_{len(placeholders)}__"
    placeholders[key] = m.group(0)
    return key

# Also protect $$...$$
content = re.sub(r'\$\$.*?\$\$', repl_math, content, flags=re.DOTALL)
content = re.sub(r'\$[^\$]*?\$', repl_math, content)

# Apply newline logic
content = re.sub(r'([①-⑩]|\([1-5]\)|(?<=\s)[1-5][\)\.])', r'\n\1', content)

# Restore math blocks
for k, v in placeholders.items():
    content = content.replace(k, v)

print(content)
