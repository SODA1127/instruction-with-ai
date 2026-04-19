import re
print("문항" == re.match(r'\w+', "문항").group())
