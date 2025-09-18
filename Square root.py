import math

def prime_factors(n):
    """Finds the prime factors of a number."""
    factors = []
    # Check for factor of 2
    while n % 2 == 0:
        factors.append(2)
        n //= 2
    # Check for odd factors
    for i in range(3, int(math.sqrt(n)) + 1, 2):
        while n % i == 0:
            factors.append(i)
            n //= i
    # If n is still greater than 2, it is a prime number
    if n > 2:
        factors.append(n)
    return factors

def square_root_by_factoring(n):
    """Calculates the square root using the factoring method."""
    factors = prime_factors(n)
    factor_count = {}
    
    # Count occurrences of each prime factor
    for factor in factors:
        factor_count[factor] = factor_count.get(factor, 0) + 1
    
    sqrt = 1  # Resultant square root
    for factor, count in factor_count.items():
        sqrt *= factor ** (count // 2)  # Include only paired factors
        
        # If there's an unpaired factor, square root is irrational
        if count % 2 != 0:
            return f"The square root of {n} is irrational."
    
    return sqrt

# Example Usage
number = int(input('enter a number to find sqrt:'))
result = square_root_by_factoring(number)
print(f"Square root of {number}: {result}")

number = int(input('enter a number to find sqrt:'))
result = square_root_by_factoring(number)
print(f"Square root of {number}: {result}")
