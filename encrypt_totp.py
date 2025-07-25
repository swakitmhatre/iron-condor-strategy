from cryptography.fernet import Fernet
import getpass

# Generate a new key
key = Fernet.generate_key()
with open("fernet.key", "wb") as f:
    f.write(key)

fernet = Fernet(key)

# Ask user for TOTP secret securely
totp_secret = getpass.getpass("Enter your 16-digit TOTP secret: ")
encrypted = fernet.encrypt(totp_secret.encode())

with open("totp_secret.enc", "wb") as f:
    f.write(encrypted)

print("TOTP secret encrypted and saved to 'totp_secret.enc'")
