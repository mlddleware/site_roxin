from bcrypt import hashpw, gensalt, checkpw

def hash_password(password: str) -> str:
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password(stored_hash: str, password: str) -> bool:
    return checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))