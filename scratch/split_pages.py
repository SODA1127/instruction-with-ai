import os
import re

source = "app/pages.py"
dest_dir = "app/pages"

with open(source, "r", encoding="utf-8") as f:
    text = f.read()

# Grab the header by splitting at the first 'def render_'
blocks = text.split("\ndef render_")
header = blocks[0]

os.makedirs(dest_dir, exist_ok=True)

modules = {
    "image_analyzer": "render_image_analyzer",
    "pdf_analyzer": "render_pdf_analyzer",
    "step_solver": "render_step_solver",
    "lesson_plan": "render_lesson_plan",
    "quiz_generator": "render_quiz_generator",
    "code_analyzer": "render_code_analyzer",
    "chatbot": "render_chatbot",
    "feedback_form": "render_feedback_form",
    "wrong_notes": "render_wrong_notes"
}

exports = []

for block in blocks[1:]:
    func_name_match = re.match(r"^(\w+)", block)
    if not func_name_match: continue
    
    func_name = "render_" + func_name_match.group(1)
    
    mod_name = None
    for k, v in modules.items():
        if v == func_name:
            mod_name = k
            break
            
    if not mod_name:
        continue
        
    full_content = header + "\n\n\ndef render_" + block
    
    with open(f"{dest_dir}/_{mod_name}.py", "w", encoding="utf-8") as f:
        f.write(full_content)
        
    exports.append(f"from ._{mod_name} import {func_name}")

with open(f"{dest_dir}/__init__.py", "w", encoding="utf-8") as f:
    f.write("\n".join(exports))

