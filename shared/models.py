from django.db import models
from django.utils import timezone
from django.conf import settings


class ContactMessage(models.Model):
    full_name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    is_replied = models.BooleanField(default=False)
    reply_message = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'
    
    def __str__(self):
        return f"{self.full_name} - {self.email}"


class SupportThread(models.Model):
    """Live support chat thread - only for authenticated company owners"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_threads'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='support_threads',
        null=True,
        blank=True
    )
    subject = models.CharField(max_length=200, default='Support request')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Support #{self.id} - {self.user.email}"


class SupportMessage(models.Model):
    """Individual message in a support thread"""
    SENDER_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
    ]

    thread = models.ForeignKey(
        SupportThread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.get_sender_type_display()} - {self.message[:50]}"