import uuid

from django.conf import settings
from django.db import models


class Account(models.Model):
    """One wallet per user. Balance is the single source of truth for money."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account"
    )
    account_number = models.CharField(max_length=20, unique=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_number} ({self.user.username}) - {self.balance}"


class Transaction(models.Model):
    """A completed money movement. Created exactly once per logical 'send'."""

    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="sent_transactions"
    )
    receiver = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="received_transactions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_COMPLETED
    )
    # Links this transaction back to the idempotency key that created it.
    # This is what lets a retried request find the ORIGINAL transaction
    # instead of creating a new one.
    idempotency_key = models.OneToOneField(
        "IdempotencyKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender_id} -> {self.receiver_id}: {self.amount} [{self.status}]"


class IdempotencyKey(models.Model):
    """
    The database-level guarantee that a given 'attempt to send' is only ever
    processed once — the real-world equivalent of the in-memory Map, but with
    a UNIQUE constraint the database itself enforces, and row locking that
    makes a race condition between two near-simultaneous duplicate requests
    physically impossible rather than just unlikely.
    """

    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    # unique=True is the actual UNIQUE constraint referenced in the README.
    key = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Which endpoint + payload this key was issued for, so a key can't be
    # replayed against a *different* request by mistake.
    request_path = models.CharField(max_length=255)
    request_fingerprint = models.CharField(max_length=64)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PROCESSING
    )
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["key"])]

    def __str__(self):
        return f"{self.key} [{self.status}]"