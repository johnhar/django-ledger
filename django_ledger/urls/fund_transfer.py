from django.urls import path

from django_ledger import views

urlpatterns = [
    path('<slug:entity_slug>/latest/',
         views.FundTransferModelListView.as_view(),
         name='fund-transfer-list'),
    path('<slug:entity_slug>/year/<int:year>/',
         views.FundTransferModelYearListView.as_view(),
         name='fund-transfer-list-year'),
    path('<slug:entity_slug>/month/<int:year>/<int:month>/',
         views.FundTransferModelMonthListView.as_view(),
         name='fund-transfer-list-month'),
    path('<slug:entity_slug>/create/',
         views.FundTransferModelCreateView.as_view(),
         name='fund-transfer-create'),
    path('<slug:entity_slug>/detail/<uuid:fund_transfer_pk>/',
         views.FundTransferModelDetailView.as_view(),
         name='fund-transfer-detail'),
    path('<slug:entity_slug>/update/<uuid:fund_transfer_pk>/',
         views.FundTransferModelUpdateView.as_view(),
         name='fund-transfer-update'),

    # Actions...
    path('<slug:entity_slug>/actions/<uuid:fund_transfer_pk>/mark-as-void/',
         views.FundTransferModelActionVoidView.as_view(),
         name='fund-transfer-action-mark-as-void'),
    path('<slug:entity_slug>/actions/<uuid:fund_transfer_pk>/lock-ledger/',
         views.FundTransferModelActionLockLedgerView.as_view(),
         name='fund-transfer-action-lock-ledger'),
    path('<slug:entity_slug>/actions/<uuid:fund_transfer_pk>/unlock-ledger/',
         views.FundTransferModelActionUnlockLedgerView.as_view(),
         name='fund-transfer-action-unlock-ledger'),
]
