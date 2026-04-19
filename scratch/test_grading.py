real_ans = "②"
user_ans = "2"
is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
print(f"real_ans: {real_ans}, user_ans: {user_ans}, is_correct: {is_correct}")

user_ans = "4"
is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
print(f"real_ans: {real_ans}, user_ans: {user_ans}, is_correct: {is_correct}")

user_ans = "②"
is_correct = real_ans in user_ans or user_ans in real_ans if user_ans else False
print(f"real_ans: {real_ans}, user_ans: {user_ans}, is_correct: {is_correct}")
