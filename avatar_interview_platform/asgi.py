"""
ASGI config for avatar_interview_platform project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""
import os
from django.core.asgi import get_asgi_application
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.middleware import BaseMiddleware
from urllib.parse import urlparse
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'avatar_interview_platform.settings')

logger = logging.getLogger(__name__)

# Initialize Django ASGI application early
django_asgi_app = get_asgi_application()


class NgrokAllowedOriginValidator(BaseMiddleware):
    """
    Custom WebSocket origin validator that allows ngrok URLs and localhost.
    This handles ngrok's browser warning page which can cause 403 errors.
    """
    
    async def __call__(self, scope, receive, send):
        # Only validate WebSocket connections
        if scope["type"] != "websocket":
            return await super().__call__(scope, receive, send)
        
        # Get the origin from headers
        origin = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"origin":
                origin = header_value.decode("utf-8")
                break

        # Allow connections without origin (can happen in some cases, e.g., Postman, curl)
        if origin is None:
            logger.debug("WebSocket connection without origin header - allowing")
            return await super().__call__(scope, receive, send)
        
        # Parse the origin URL
        try:
            parsed_origin = urlparse(origin)
            origin_host = parsed_origin.hostname
            
            # Get allowed hosts from settings
            allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
            debug_mode = getattr(settings, 'DEBUG', False)
            # Frontend origin (e.g. Vercel) - allow WebSocket connections from FRONTEND_URL
            frontend_url = getattr(settings, 'FRONTEND_URL', '') or ''
            frontend_host = urlparse(frontend_url).hostname if frontend_url else None
            extra_origin_hosts = getattr(settings, 'WEBSOCKET_EXTRA_ALLOWED_ORIGIN_HOSTS', []) or []

            # Check if origin is allowed
            # Allow ngrok, localhost, ALLOWED_HOSTS, FRONTEND_URL host, extra list, or DEBUG
            is_allowed = (
                debug_mode or  # In DEBUG mode, allow all origins for easier development
                origin_host in allowed_hosts or
                origin_host == frontend_host or
                origin_host in extra_origin_hosts or
                origin_host is None or
                any(origin_host.endswith(domain) for domain in ['.ngrok-free.app', '.ngrok.io', '.ngrok.app', '.ngrok-free.app', '.vercel.app']) or
                origin_host in ['localhost', '127.0.0.1'] or
                '*' in allowed_hosts
            )
            
            if not is_allowed:
                logger.warning(f"WebSocket connection rejected from origin: {origin}")
                await send({
                    "type": "websocket.close",
                    "code": 4004,
                })
                return
            
            logger.debug(f"WebSocket connection allowed from origin: {origin}")
            
        except Exception as e:
            logger.error(f"Error validating WebSocket origin: {e}")
            # For development, allow connection if validation fails
            # This is important for ngrok which can have origin issues
        
        return await super().__call__(scope, receive, send)


# Import routing after django setup
from meetings.routing import websocket_urlpatterns as meetings_urlpatterns
from notifications.routing import websocket_urlpatterns as notifications_urlpatterns

from avatar_interview_platform.middleware import JWTAuthMiddleware

websocket_urlpatterns = meetings_urlpatterns + notifications_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": NgrokAllowedOriginValidator(
        AuthMiddlewareStack(
            JWTAuthMiddleware(
                URLRouter(websocket_urlpatterns)
            )
        )
    ),
})