import phonenumbers
from rest_framework import serializers

def validate_phone_number(value):
    if not value or not isinstance(value, str):
        raise serializers.ValidationError("Phone number must be a non-empty string.")

    try:
        phone_number = phonenumbers.parse(value, None)  # No default region
    except phonenumbers.NumberParseException:
        raise serializers.ValidationError("Invalid phone number format.")

    if not phonenumbers.is_possible_number(phone_number):
        raise serializers.ValidationError("Phone number is not possible.")
    
    if not phonenumbers.is_valid_number(phone_number):
        raise serializers.ValidationError("Phone number is not valid.")
    
    return phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.E164)