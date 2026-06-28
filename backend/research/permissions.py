from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Object-level guard enforcing per-user data isolation (FR-AUTH-5).

    Defence in depth: querysets are already scoped to ``request.user`` in the
    views, but this also rejects any object whose owner is not the caller.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id
