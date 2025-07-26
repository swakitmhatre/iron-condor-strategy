from cryptography.fernet import Fernet
import base64

# Step 1: Input your actual 16-character base32 TOTP secret
totp_secret = input("Enter your 16-character TOTP secret: ").strip()

# Step 2: Generate encryption key
key = Fernet.generate_key()
fernet = Fernet(key)

# Step 3: Encrypt the secret
encrypted_secret = fernet.encrypt(totp_secret.encode())

# Step 4: Save both key and encrypted secret to files
with open("fernet_key.key", "wb") as fk:
    fk.write(key)

with open("encrypted_totp.txt", "wb") as et:
    et.write(encrypted_secret)

print("✅ Encrypted TOTP secret and key saved.")
