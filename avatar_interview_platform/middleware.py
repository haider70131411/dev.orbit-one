import json
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from urllib.parse import parse_qs

@database_sync_to_async
def get_user(token_key):
    User = get_user_model()
    try:
        token = AccessToken(token_key)
        user_id = token['user_id']
        return User.objects.get(id=user_id)
    except Exception as e:
        print(f"WebSocket JWT Auth Error: {str(e)}")
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    Custom middleware that takes token from the query string and authenticates the user.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Get the token from query string
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get('token', [None])[0]
        
        print(f"DEBUG: JWTAuthMiddleware called. Token found: {bool(token_key)}")

        if token_key:
            scope['user'] = await get_user(token_key)
            print(f"DEBUG: User authenticated: {scope['user']}")
        else:
            scope['user'] = AnonymousUser()
            print("DEBUG: User is Anonymous")

        return await self.inner(scope, receive, send)
