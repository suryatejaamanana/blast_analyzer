from services.user_service import create_user

def post_user(request):
    username = request.get("username")
    age = request.get("age")
    return create_user(username, age)
