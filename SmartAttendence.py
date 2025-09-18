#38c2f17ffe9cc7c7e78e962581b0e49b178f129b4e9af1a79b18d440c0338306
import hashlib

# Change 'your_new_password' to any password you want
password = 'VITBPL' 

hashed_password = hashlib.sha256(password.encode()).hexdigest()
print(hashed_password)