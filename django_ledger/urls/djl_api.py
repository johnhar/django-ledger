from django.urls import path

from django_ledger import views

urlpatterns = [
    # Entity API URLs
    path('entity/<slug:entity_slug>/data/pnl/',
         views.PnLAPIView.as_view(),
         name='entity-json-pnl'),
    path('entity/<slug:entity_slug>/data/net-payables/',
         views.PayableNetAPIView.as_view(),
         name='entity-json-net-payables'),
    path('entity/<slug:entity_slug>/data/net-receivables/',
         views.ReceivableNetAPIView.as_view(),
         name='entity-json-net-receivables'),

    # Entity Unit API URLs
    path('unit/<slug:entity_slug>/<slug:unit_slug>/data/pnl/',
         views.PnLAPIView.as_view(),
         name='unit-json-pnl'),
    path('unit/<slug:entity_slug>/<slug:unit_slug>/data/net-payables/',
         views.PayableNetAPIView.as_view(),
         name='unit-json-net-payables'),
    path('unit/<slug:entity_slug>/<slug:unit_slug>/data/net-receivables/',
         views.ReceivableNetAPIView.as_view(),
         name='unit-json-net-receivables'),

    # Fund API URLs
    path('fund/<slug:entity_slug>/<slug:fund_slug>/data/pnl/',
         views.PnLAPIView.as_view(),
         name='fund-json-pnl'),
    path('fund/<slug:entity_slug>/<slug:fund_slug>/data/net-payables/',
         views.PayableNetAPIView.as_view(),
         name='fund-json-net-payables'),
    path('fund/<slug:entity_slug>/<slug:fund_slug>/data/net-receivables/',
         views.ReceivableNetAPIView.as_view(),
         name='fund-json-net-receivables'),
]
