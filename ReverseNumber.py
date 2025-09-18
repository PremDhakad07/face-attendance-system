# Function to reverse the digits of a two-digit number
def reverse_number(num):
    tens = num // 10
    units = num % 10
    reversed_num = (units * 10) + tens
    return reversed_num

# Input two-digit number
num = int(input("Enter a two-digit number: "))

if num < 10 or num > 99:
    print("Please enter a valid two-digit number.")
else:
    reversed_num = reverse_number(num)
    
    if reversed_num > num:
        result = reversed_num - num
        print("The reversed number",reversed_num, "is greater than the input number",num,". The difference is" , result)
    else:
        result = reversed_num + num
        print("The reversed number",reversed_num,"is not greater than the input number",num,". The sum is", result)
