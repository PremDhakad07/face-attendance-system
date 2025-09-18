def diamond_pattern(n):

    for i in range(1, n + 1):
        print(("*" * (2 * i - 1)).center(2 * n - 1)) 

    for i in range(n - 1, 0, -1):
        print(("*" * (2 * i - 1)).center(2 * n - 1))  


n = int(input("Enter number of rows:"))
diamond_pattern(n)