from utils.validation import validate_user
from models.user_model import User
from database.db import save_user

def create_user(username, age):
    if not validate_user(username, age):
        return {"error": "Invalid data"}
    
    user = User(username, age)
    save_user(user)
    return {"status": "success"}
