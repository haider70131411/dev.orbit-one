# admin_app/serializers.py
from django.contrib.auth import get_user_model
from accounts.serializers import UserRegistrationSerializer, SetNewPasswordSerializer
from rest_framework import serializers
from companies.models import Company, CompanyPerson
from meetings.models import Meeting, MeetingParticipant, MeetingFeedback

User = get_user_model()


class AdminUserListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'is_active', 'is_staff', 'company_name'
        ]


class AdminCompanyListSerializer(serializers.ModelSerializer):
    admin_email = serializers.SerializerMethodField()
    has_smtp = serializers.SerializerMethodField()
    meetings_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'company_type', 'industry', 'status',
            'admin_email', 'has_smtp', 'meetings_count',
            'created_at', 'updated_at'
        ]

    def get_admin_email(self, obj):
        return obj.admin_user.email if hasattr(obj, 'admin_user') and obj.admin_user else None

    def get_has_smtp(self, obj):
        return obj.has_smtp_config()

    def get_meetings_count(self, obj):
        return getattr(obj, 'meetings_count', obj.meetings.count())


class AdminCompanyDetailSerializer(serializers.ModelSerializer):
    admin_details = serializers.SerializerMethodField()
    has_smtp = serializers.SerializerMethodField()
    people_count = serializers.SerializerMethodField()
    meetings_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'company_type', 'industry', 'website', 'logo', 'description',
            'status', 'rejection_remarks',
            'address_country', 'address_city', 'address_street', 'address_postal',
            'contact_number', 'support_email',
            'admin_details', 'has_smtp', 'people_count', 'meetings_count',
            'created_at', 'updated_at'
        ]

    def get_admin_details(self, obj):
        if hasattr(obj, 'admin_user') and obj.admin_user:
            u = obj.admin_user
            return {'id': u.id, 'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name}
        return None

    def get_has_smtp(self, obj):
        return obj.has_smtp_config()

    def get_people_count(self, obj):
        return obj.people.count()

    def get_meetings_count(self, obj):
        return obj.meetings.count()


class AdminMeetingParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingParticipant
        fields = ['id', 'participant_type', 'name', 'email', 'joined_at', 'left_at']


class AdminMeetingFeedbackSerializer(serializers.ModelSerializer):
    interviewer_name = serializers.CharField(source='interviewer.name', read_only=True)

    class Meta:
        model = MeetingFeedback
        fields = ['id', 'interviewer_name', 'rating', 'behavioral_score', 'technical_score', 'feedback_text', 'created_at']


class AdminMeetingListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    interviewer_names = serializers.SerializerMethodField()
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id', 'title', 'status', 'company_name', 'interviewer_names',
            'interviewee_name', 'interviewee_email', 'scheduled_date', 'scheduled_time',
            'duration_minutes', 'meeting_room_id', 'join_url',
            'enable_recording', 'recording_file', 'recording_status',
            'created_at', 'updated_at'
        ]

    def get_interviewer_names(self, obj):
        return [i.name for i in obj.interviewers.all()]

    def get_scheduled_date(self, obj):
        return obj.scheduled_date

    def get_scheduled_time(self, obj):
        return obj.scheduled_time.strftime('%H:%M:%S')


class AdminMeetingDetailSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    interviewer_names = serializers.SerializerMethodField()
    interviewer_emails = serializers.SerializerMethodField()
    participants = AdminMeetingParticipantSerializer(many=True, read_only=True)
    feedbacks = AdminMeetingFeedbackSerializer(many=True, read_only=True)
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id', 'title', 'description', 'status', 'company_name',
            'interviewer_names', 'interviewer_emails',
            'interviewee_name', 'interviewee_email', 'interviewee_phone',
            'scheduled_date', 'scheduled_time', 'duration_minutes',
            'meeting_room_id', 'join_url',
            'participants', 'feedbacks',
            'enable_recording', 'recording_file', 'recording_status',
            'created_at', 'updated_at'
        ]

    def get_interviewer_names(self, obj):
        return [i.name for i in obj.interviewers.all()]

    def get_interviewer_emails(self, obj):
        return [i.email for i in obj.interviewers.all()]

    def get_scheduled_date(self, obj):
        return obj.scheduled_date

    def get_scheduled_time(self, obj):
        return obj.scheduled_time.strftime('%H:%M:%S')
