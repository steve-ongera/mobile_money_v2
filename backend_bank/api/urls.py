from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("accounts/me/", views.AccountView.as_view(), name="account-me"),
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    path("transactions/send/", views.SendMoneyView.as_view(), name="transaction-send"),
]