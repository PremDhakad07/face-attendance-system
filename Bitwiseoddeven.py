def is_even(number):
    # Using bitwise AND operator to check if the least significant bit is 0
    if (number & 1) == 0:
        return True
    else:
        return False

# Example usage
number = int(input("Enter a number:"))

if is_even(number):
    print(number, "is even.")
else:
    print(number, "is odd.")
