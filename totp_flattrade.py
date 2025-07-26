from cryptography.fernet import Fernet

key = Fernet.generate_key()
print("FERNET_KEY =", key)

fernet = Fernet(key)
encrypted = fernet.encrypt(b"your_16_digit_base32_totp_secret")
print("ENCRYPTED_TOTP =", encrypted)
