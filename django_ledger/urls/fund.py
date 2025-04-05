from django.urls import path

from django_ledger import views

urlpatterns = [
    path('<slug:entity_slug>/fund/list/',
         views.FundModelListView.as_view(),
         name='fund-list'),
    path('<slug:entity_slug>/detail/<slug:fund_slug>/',
         views.FundModelDetailView.as_view(),
         name='fund-detail'),
    path('<slug:entity_slug>/fund/create/',
         views.FundModelCreateView.as_view(),
         name='fund-create'),
    path('<slug:entity_slug>/fund/update/<slug:fund_slug>/',
         views.FundUpdateView.as_view(),
         name='fund-update'),


    # DASHBOARD Views ...
    path('<slug:entity_slug>/dashboard/<slug:fund_slug>/',
         views.EntityModelDetailHandlerView.as_view(),
         name='fund-dashboard'),
    path('<slug:entity_slug>/dashboard/<slug:fund_slug>/year/<int:year>/',
         views.FiscalYearEntityModelDashboardView.as_view(),
         name='fund-dashboard-year'),
    path('<slug:entity_slug>/dashboard/<slug:fund_slug>/quarter/<int:year>/<int:quarter>/',
         views.QuarterlyEntityDashboardView.as_view(),
         name='fund-dashboard-quarter'),
    path('<slug:entity_slug>/dashboard/<slug:fund_slug>/month/<int:year>/<int:month>/',
         views.MonthlyEntityDashboardView.as_view(),
         name='fund-dashboard-month'),
    path('<slug:entity_slug>/dashboard/<slug:fund_slug>/date/<int:year>/<int:month>/<int:day>/',
         views.DateEntityDashboardView.as_view(),
         name='fund-dashboard-date'),

]
