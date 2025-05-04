"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.
"""


from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DetailView, RedirectView

from django_ledger.forms.fund import FundModelCreateForm, FundModelUpdateForm
from django_ledger.io.utils import get_localdate
from django_ledger.models import FundModel, EntityModel
from django_ledger.views.financial_statement import FiscalYearIncomeStatementView
from django_ledger.views.mixins import (DjangoLedgerSecurityMixIn, QuarterlyReportMixIn, MonthlyReportMixIn,
                                        DateReportMixIn, BaseDateNavigationUrlMixIn, FundMixIn, YearlyReportMixIn,
                                        PDFReportMixIn)


class FundModelModelBaseView(DjangoLedgerSecurityMixIn):
    queryset = None

    # noinspection PyUnresolvedReferences
    def get_queryset(self):
        if self.queryset is None:
            self.queryset = FundModel.objects.for_entity(
                entity_slug=self.kwargs['entity_slug'],
                user_model=self.request.user
            ).select_related('entity')
        return super().get_queryset()


class FundModelListView(FundModelModelBaseView, ListView):
    template_name = 'django_ledger/fund/fund_list.html'
    PAGE_TITLE = _('Fund List')
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        # 'header_subtitle_icon': 'dashicons:businesswoman'
    }
    context_object_name = 'fund_list'


class FundModelDetailView(FundModelModelBaseView, DetailView):
    template_name = 'django_ledger/fund/fund_detail.html'
    PAGE_TITLE = _('Fund Detail')
    slug_url_kwarg = 'fund_slug'
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        # 'header_subtitle_icon': 'dashicons:businesswoman'
    }
    context_object_name = 'fund'


class FundModelCreateView(FundModelModelBaseView, CreateView):
    template_name = 'django_ledger/fund/fund_create.html'
    PAGE_TITLE = _('Fund Create')
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        # 'header_subtitle_icon': 'dashicons:businesswoman'
    }

    def get_form(self, form_class=None):
        return FundModelCreateForm(
            entity_slug=self.kwargs['entity_slug'],
            user_model=self.request.user,
            **self.get_form_kwargs()
        )

    def get_success_url(self):
        return reverse('django_ledger:fund-list',
                       kwargs={
                           'entity_slug': self.kwargs['entity_slug']
                       })

    def form_valid(self, form):
        fund_model: FundModel = form.save(commit=False)
        entity_model_qs = EntityModel.objects.for_user(user_model=self.request.user)
        entity_model = get_object_or_404(entity_model_qs, slug__exact=self.kwargs['entity_slug'])
        fund_model.entity = entity_model
        FundModel.add_root(instance=fund_model)
        return HttpResponseRedirect(self.get_success_url())


class FundUpdateView(FundModelModelBaseView, UpdateView):
    template_name = 'django_ledger/fund/fund_update.html'
    PAGE_TITLE = _('Fund Update')
    slug_url_kwarg = 'fund_slug'
    context_object_name = 'fund'
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        # 'header_subtitle_icon': 'dashicons:businesswoman'
    }

    def get_form(self, form_class=None):
        return FundModelUpdateForm(
            entity_slug=self.kwargs['entity_slug'],
            user_model=self.request.user,
            **self.get_form_kwargs()
        )

    def get_success_url(self):
        return reverse('django_ledger:fund-list',
                       kwargs={
                           'entity_slug': self.kwargs['entity_slug']
                       })

    def form_valid(self, form):
        instance: FundModel = form.save(commit=False)
        instance.clean()
        form.save()
        return super().form_valid(form=form)


# Financial Statements...


# BALANCE SHEET.....
class BaseFundModelBalanceSheetView(FundModelModelBaseView, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        year = get_localdate().year
        return reverse('django_ledger:fund-bs-year',
                       kwargs={
                           'entity_slug': self.kwargs['entity_slug'],
                           'fund_slug': self.kwargs['fund_slug'],
                           'year': year
                       })


class FiscalYearFundModelBalanceSheetView(FundModelModelBaseView,
                                                BaseDateNavigationUrlMixIn,
                                                FundMixIn,
                                                YearlyReportMixIn,
                                                PDFReportMixIn,
                                                DetailView):
    """
    Fund Fiscal Year Balance Sheet View Class
    """

    context_object_name = 'fund_model'
    slug_url_kwarg = 'fund_slug'
    template_name = 'django_ledger/financial_statements/balance_sheet.html'
    pdf_report_type = 'BS'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_model'] = self.object.entity
        return context


class QuarterlyFundModelBalanceSheetView(FiscalYearFundModelBalanceSheetView, QuarterlyReportMixIn):
    """
    Fund Fiscal Quarter Balance Sheet View Class.
    """


class MonthlyFundModelBalanceSheetView(FiscalYearFundModelBalanceSheetView, MonthlyReportMixIn):
    """
    Fund Fiscal Month Balance Sheet View Class.
    """


class DateFundModelBalanceSheetView(MonthlyFundModelBalanceSheetView, DateReportMixIn):
    """
    Fund Date Balance Sheet View Class.
    """


# INCOME STATEMENT....
class BaseFundModelIncomeStatementView(FundModelModelBaseView, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        year = get_localdate().year
        return reverse('django_ledger:fund-ic-year',
                       kwargs={
                           'entity_slug': self.kwargs['entity_slug'],
                           'fund_slug': self.kwargs['fund_slug'],
                           'year': year
                       })


class FiscalYearFundModelIncomeStatementView(FundModelModelBaseView,
                                                   BaseDateNavigationUrlMixIn,
                                                   FundMixIn,
                                                   YearlyReportMixIn,
                                                   PDFReportMixIn,
                                                   DetailView):
    context_object_name = 'fund_model'
    slug_url_kwarg = 'fund_slug'
    template_name = 'django_ledger/financial_statements/income_statement.html'
    pdf_report_type = 'IS'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_model'] = self.object.entity
        return context


class QuarterlyIncomeStatementView(FiscalYearIncomeStatementView, QuarterlyReportMixIn):
    """
    Fund Fiscal Quarter Income Statement View Class
    """


class MonthlyIncomeStatementView(FiscalYearIncomeStatementView, MonthlyReportMixIn):
    """
    Fund Fiscal Month Income Statement View Class
    """


class DateIncomeStatementView(FiscalYearIncomeStatementView, DateReportMixIn):
    """
    Fund Date Income Statement View Class
    """


# CASHFLOW STATEMENT
class BaseFundModelCashFlowStatementView(FundModelModelBaseView, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        year = get_localdate().year
        return reverse('django_ledger:fund-cf-year',
                       kwargs={
                           'entity_slug': self.kwargs['entity_slug'],
                           'fund_slug': self.kwargs['fund_slug'],
                           'year': year
                       })


class FiscalYearFundModelCashFlowStatementView(FundModelModelBaseView,
                                                     BaseDateNavigationUrlMixIn,
                                                     FundMixIn,
                                                     YearlyReportMixIn,
                                                     PDFReportMixIn,
                                                     DetailView):
    context_object_name = 'fund_model'
    slug_url_kwarg = 'fund_slug'
    template_name = 'django_ledger/financial_statements/cash_flow.html'
    pdf_report_type = 'CFS'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_model'] = self.object.entity
        return context


class QuarterlyFundModelCashFlowStatementView(FiscalYearFundModelCashFlowStatementView,
                                                    QuarterlyReportMixIn):
    """
    Fund Fiscal Quarter Cash Flow Statement View Class
    """


class MonthlyFundModelCashFlowStatementView(FiscalYearFundModelCashFlowStatementView,
                                                  MonthlyReportMixIn):
    """
    Fund Fiscal Month Cash Flow Statement View Class
    """


class DateFundModelCashFlowStatementView(FiscalYearFundModelCashFlowStatementView,
                                               DateReportMixIn):
    """
    Fund Date Cash Flow Statement View Class
    """
