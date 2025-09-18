import math

def finding_perfect_square(number):

    if number<0:
        return None

    square_root= int(math.sqrt(number))
    if square_root*square_root == number:
        return square_root
    
    else:
        return None
    
number = int(input("Enter a number :"))
result = finding_perfect_square(number)

if result is not None:
    print("The perfect square of", number , "is", result)

else:
    print(number ,"is not a perfect square")
    