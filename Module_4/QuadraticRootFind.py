import math

def find_roots(a, b, c):
    discriminant = b**2 - 4*a*c
    if discriminant > 0:
        root1 = (-b + math.sqrt(discriminant)) / (2*a)
        root2 = (-b - math.sqrt(discriminant)) / (2*a)
        return f"Roots are real and distinct: {root1} and {root2}"
    elif discriminant == 0:
        root = -b / (2*a)
        return f"Roots are real and equal: {root}"
    else:
        real_part = -b / (2*a)
        imaginary_part = math.sqrt(-discriminant) / (2*a)
        return f"Roots are complex: {real_part} ± {imaginary_part}i"

# Example
a = 1
b = -5
c = 6
print(find_roots(a, b, c))
