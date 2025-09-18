def second_largest_digit(number):
    digit_num = str(number)
    digits = set(int(number) for number in digit_num)

    if len(digits)<2:
        return None
    
    digits.remove(max(digits))
    second_largest= max(digits)
    return second_largest
number= int(input("Enter a number:"))
result= second_largest_digit(number)

if result is not None:
    print("The second largest digit of", number,"is ",result)
else:
    print("There are not enough unique digit to determine 2nd smallest digit") 