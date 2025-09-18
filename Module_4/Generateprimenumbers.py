import math
def is_prime(number):
    if number<=1:
        return False
    for i in range(2,int(math.sqrt(number))+1):
        if number%i==0:
            return False
    return True
number=int(input("Enter a number:"))
result=is_prime(number)

if result is True:
    print(number,"is a prime number.")
else:
    print(number,"is not a prime number.")