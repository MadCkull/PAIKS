from django.db import models
from django.utils import timezone

class DocumentTrack(models.Model):
    SYNC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('syncing', 'Syncing'),
        ('synced', 'Synced'),
        ('error', 'Error'),
        ('disabled', 'Disabled'),
    ]
    
    SOURCE_CHOICES = [
        ('cloud', 'Google Drive'),
        ('local', 'Local File'),
    ]

    file_id = models.CharField(max_length=1024, unique=True, help_text="Google Drive ID or Local File Path")
    name = models.CharField(max_length=512)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    
    is_selected = models.BooleanField(default=True, help_text="True if the user wants this file indexed")
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default='pending')
    
    content_hash = models.CharField(max_length=128, null=True, blank=True, help_text="SHA-256 hash to detect local file changes")
    last_modified = models.DateTimeField(null=True, blank=True, help_text="Last modified time from OS or Cloud")
    error_message = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"[{self.source.upper()}] {self.name} - {self.sync_status}"

class SyncJob(models.Model):
    """
    Outbox pattern queue for background processing.
    Ensures that Qdrant index/delete operations are persistent and survive restarts.
    """
    ACTION_CHOICES = [
        ('index', 'Index'),
        ('delete', 'Delete'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    document = models.ForeignKey(DocumentTrack, on_delete=models.CASCADE, related_name='jobs')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.action.upper()} | {self.document.name} | {self.status}"

class ChatSession(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title[:30]} ({self.id})"

class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('ai', 'AI'),
        ('system', 'System'),
    ]
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(null=True, blank=True, help_text="Stores citations, styling info, and search hits")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role.upper()}] {self.content[:30]}"
