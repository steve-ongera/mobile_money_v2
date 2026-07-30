import random

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .idempotency import idempotent
from .models import Account, Transaction
from .serializers import (
    AccountSerializer,
    SendMoneySerializer,
    TransactionSerializer,
)

User = get_user_model()


def _generate_account_number():
    while True:
        number = str(random.randint(10**9, 10**10 - 1))
        if not Account.objects.filter(account_number=number).exists():
            return number


class LoginView(APIView):
    """
    POST /api/auth/login/  {"username": "...", "password": "..."}

    Mock auth, matching the original project: any username/password pair is
    accepted. First login for a username creates the user and a funded demo
    account. Returns a DRF auth token to use as:
        Authorization: Token <token>
    """

    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response(
                {"error": "username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_unusable_password()
            user.save()
            Account.objects.create(
                user=user,
                account_number=_generate_account_number(),
                balance=Decimal("1000.00"),  # demo starting balance
            )

        token, _ = Token.objects.get_or_create(user=user)
        account = Account.objects.get(user=user)
        return Response(
            {
                "token": token.key,
                "account": AccountSerializer(account).data,
            }
        )


class AccountView(APIView):
    """GET /api/accounts/me/ — the logged-in user's own account."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        account = Account.objects.get(user=request.user)
        return Response(AccountSerializer(account).data)


class TransactionListView(APIView):
    """GET /api/transactions/ — every completed transfer the user sent or received."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        account = Account.objects.get(user=request.user)
        qs = Transaction.objects.filter(
            Q(sender=account) | Q(receiver=account)
        ).select_related("sender", "receiver")
        return Response(TransactionSerializer(qs, many=True).data)


class SendMoneyView(APIView):
    """
    POST /api/transactions/send/
    Headers: Idempotency-Key: <client-generated uuid, one per "attempt to send">
    Body: {"receiver_account_number": "...", "amount": "10.00"}

    This is the endpoint the README calls "the single most dangerous button
    in the UI". Two things make a duplicate tap/retry/timeout harmless:

      1. @idempotent — no matter how many times this exact attempt reaches
         the server, the body below runs at most once (see idempotency.py).
      2. select_for_update() on both accounts, taken in a fixed order
         (lowest account id first) — this is what a real UNIQUE constraint
         + row-level locking / SERIALIZABLE transaction buys you, and it's
         what stops a *balance* race even independent of the idempotency
         key (e.g. two different legitimate transfers touching the same
         account at the same instant).
    """

    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request):
        serializer = SendMoneySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data["amount"]
        receiver_account_number = serializer.validated_data["receiver_account_number"]

        try:
            sender_account = Account.objects.get(user=request.user)
        except Account.DoesNotExist:
            return Response(
                {"error": "Sender account not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if sender_account.account_number == receiver_account_number:
            return Response(
                {"error": "Cannot send money to your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():
            # Lock both rows in a stable order (by primary key) so two
            # concurrent transfers that both touch these two accounts can
            # never deadlock against each other.
            ids = sorted(
                Account.objects.filter(
                    account_number__in=[sender_account.account_number, receiver_account_number]
                ).values_list("id", flat=True)
            )
            locked_accounts = {
                a.id: a
                for a in Account.objects.select_for_update().filter(id__in=ids)
            }
            sender = next(
                a for a in locked_accounts.values()
                if a.account_number == sender_account.account_number
            )
            receiver = next(
                a for a in locked_accounts.values()
                if a.account_number == receiver_account_number
            )

            if sender.balance < amount:
                return Response(
                    {"error": "Insufficient balance."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sender.balance -= amount
            receiver.balance += amount
            sender.save(update_fields=["balance"])
            receiver.save(update_fields=["balance"])

            txn = Transaction.objects.create(
                sender=sender,
                receiver=receiver,
                amount=amount,
                status=Transaction.STATUS_COMPLETED,
            )

        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)