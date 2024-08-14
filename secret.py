import secrets

# Gera uma chave secreta de 32 bytes em hexadecimal
secret_key = secrets.token_hex(32)
print(secret_key)