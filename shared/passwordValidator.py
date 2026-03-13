
import re
from rest_framework import serializers

def validate_password_strength(value):
    if len(value) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters long.")

    if not re.search(r"[A-Za-z]", value):
        raise serializers.ValidationError("Password must contain at least one letter.")

    if not re.search(r"\d", value):
        raise serializers.ValidationError("Password must contain at least one number.")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise serializers.ValidationError("Password must contain at least one special character.")

    return value
