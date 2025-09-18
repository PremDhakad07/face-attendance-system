def smallestDivisior(n):

    if n % 2 == 0:
        return 2
    
    i=3
    while (i*i <= n):
        if (n % i ==0):
            return i
        i = i + 2
    return n

n = int(input("Enter a number:"))
result = smallestDivisior(n)

print("Smallest Divisior of",n,"is",result)
if result == 1:
    print(n,"is not a prime number")
elif result == n:
    print(n,"is a prime number")
else:
    print(n,"is not a prime number")