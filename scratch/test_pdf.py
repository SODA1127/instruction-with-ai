import os
import sys
import io

# Add parent directory to path to import src
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), ".")))

try:
    from src.app_utils import make_pdf_bytes
    print("Import successful")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

test_md = """
# 테스트 문서
안녕하세요. 이것은 PDF 생성 테스트입니다.
[ANSWER_START]
정답: 1번
해설: 테스트입니다.
[ANSWER_END]
"""

print("Generating PDF...")
pdf_bytes = make_pdf_bytes(test_md)

if pdf_bytes:
    print(f"Success! PDF size: {len(pdf_bytes)} bytes")
    # Save to file to verify
    with open("test_output.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("Saved to test_output.pdf")
else:
    print("FAILED: make_pdf_bytes returned None")

# Test with thinking block
test_md_thinking = "<think>This is a thought that should be removed.</think># 본문 내용"
print("\nTesting with thinking block...")
pdf_bytes_2 = make_pdf_bytes(test_md_thinking)
if pdf_bytes_2:
    print(f"Success! PDF size: {len(pdf_bytes_2)} bytes")
else:
    print("FAILED with thinking block")
