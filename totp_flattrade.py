from cryptography.fernet import Fernet

key = Fernet.generate_key()
print("FERNET_KEY =", key)

fernet = Fernet(key)
encrypted = fernet.encrypt(b"25N7JNC523GRANMPRVXYH72PDW7P25JZ")
print("ENCRYPTED_TOTP =", encrypted)
