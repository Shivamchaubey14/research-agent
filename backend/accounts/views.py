from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register — create an account (FR-AUTH-1)."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """POST /api/v1/auth/token — obtain access + refresh tokens (FR-AUTH-2)."""

    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    """POST /api/v1/auth/token/refresh — rotate the access token (FR-AUTH-4)."""

    throttle_scope = "auth"


class MeView(APIView):
    """GET /api/v1/auth/me — the current authenticated user's profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
