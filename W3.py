def is_prime(number):
    if number <= 1:
        return False
    
    for i in range(2,number):
        if number%i==0:
            return False
    
    return True


for number in range(1,101):
    if is_prime(number):
        print(number,end=" ")

