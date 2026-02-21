def validate_user(username, age):
    if not username:
        return False
    if age < 18:
        return False
    return True
