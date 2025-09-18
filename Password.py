def validate_password(password):
    # Conditions to check
    has_lower = False  # At least one lowercase letter
    has_upper = False  # At least one uppercase letter
    has_digit = False  # At least one digit
    has_special = False  # At least one special character from $, #, @
    min_length = 6  # Minimum length
    max_length = 12  # Maximum length
    
    # Special characters allowed
    special_characters = "$#@"

    # Check the length of the password
    if not (min_length <= len(password) <= max_length):
        return "Invalid password"

    # Iterate through each character in the password
    for char in password:
        if char.islower():
            has_lower = True
        elif char.isupper():
            has_upper = True
        elif char.isdigit():
            has_digit = True
        elif char in special_characters:
            has_special = True

    # Verify all conditions are satisfied
    if has_lower and has_upper and has_digit and has_special:
        return "Valid password"
    else:
        return "Invalid password"


# Input from user
password = input("Enter a password: ")

# Validate the password
result = validate_password(password)
print(result)
