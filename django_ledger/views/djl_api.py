"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

Contributions to this module:
    * Miguel Sanda <msanda@arrobalytics.com>
"""

from calendar import month_name

from django.http import JsonResponse
from django.views.generic import View

from django_ledger.models import BillModel, EntityModel, InvoiceModel
from django_ledger.utils import accruable_net_summary
from django_ledger.views.mixins import DjangoLedgerSecurityMixIn, EntityUnitMixIn, FundMixIn


# from jsonschema import validate, ValidationError


class PnLAPIView(DjangoLedgerSecurityMixIn, EntityUnitMixIn, FundMixIn, View):
    http_method_names = ['get']

    def get_context_data(self, **kwargs):
        if EntityUnitMixIn.UNIT_SLUG_KWARG in self.kwargs:
            # Call the EntityUnitMixIn's get_context_data() explicitly
            context = EntityUnitMixIn.get_context_data(self, **kwargs)
            print(f'PnLAPIView using unit dashboard context')   # TODO JJH remove
        elif FundMixIn.FUND_SLUG_KWARG in self.kwargs:
            # Call the FundMixIn's get_context_data() explicitly
            context = FundMixIn.get_context_data(self, **kwargs)
            print(f'PnLAPIView using fund dashboard context')   # TODO JJH remove
        else:
            # Default behavior if neither match
            context = super().get_context_data(**kwargs)
            print(f'PnLAPIView using entity dashboard context')   # TODO JJH remove

        return context

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            entity = EntityModel.objects.for_user(
                user_model=self.request.user).get(
                slug__exact=self.kwargs['entity_slug'])

            unit_slug = self.get_unit_slug()
            fund_slug = self.get_fund_slug()
            print(f'PnLAPIView unit_slug: {unit_slug}')   # TODO JJH remove
            print(f'PnLAPIView fund_slug: {fund_slug}')   # TODO JJH remove

            io_digest = entity.digest(
                user_model=self.request.user,
                unit_slug=unit_slug,
                fund_slug=fund_slug,
                equity_only=True,
                signs=False,
                by_period=True,
                process_groups=True,
                from_date=self.request.GET.get('fromDate'),
                to_date=self.request.GET.get('toDate'),

                # todo: For PnL to display proper period values must not use closing entries.
                use_closing_entries=False
            )

            io_data = io_digest.get_io_data()
            group_balance_by_period = io_data['group_balance_by_period']
            group_balance_by_period = dict(sorted((k, v) for k, v in group_balance_by_period.items()))

            entity_data = {
                f'{month_name[k[1]]} {k[0]}': {d: float(f) for d, f in v.items()} for k, v in
                group_balance_by_period.items()}

            entity_pnl = {
                'entity_slug': entity.slug,
                'entity_name': entity.name,
                'pnl_data': entity_data
            }

            return JsonResponse({
                'results': entity_pnl
            })

        return JsonResponse({
            'message': 'Unauthorized'
        }, status=401)


class PayableNetAPIView(DjangoLedgerSecurityMixIn, EntityUnitMixIn, FundMixIn, View):
    http_method_names = ['get']

    def get_context_data(self, **kwargs):
        if EntityUnitMixIn.UNIT_SLUG_KWARG in self.kwargs:
            # Call the EntityUnitMixIn's get_context_data() explicitly
            context = EntityUnitMixIn.get_context_data(self, **kwargs)
            print(f'PayableNetAPIView using unit dashboard context')   # TODO JJH remove
        elif FundMixIn.FUND_SLUG_KWARG in self.kwargs:
            # Call the FundMixIn's get_context_data() explicitly
            context = FundMixIn.get_context_data(self, **kwargs)
            print(f'PayableNetAPIView using fund dashboard context')   # TODO JJH remove
        else:
            # Default behavior if neither match
            context = super().get_context_data(**kwargs)
            print(f'PayableNetAPIVie wusing entity dashboard context')   # TODO JJH remove

        return context

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            bill_qs = BillModel.objects.for_entity(
                entity_slug=self.kwargs['entity_slug'],
                user_model=request.user,
            ).unpaid()

            # todo: implement this...
            unit_slug = self.get_unit_slug()
            # if unit_slug:
            #     bill_qs.filter(ledger__journal_entry__entity_unit__slug__exact=unit_slug)
            # todo: implement this too.
            fund_slug = self.get_fund_slug()
            # if fund_slug:
            #     bill_qs.filter(ledger__journal_entry__?__exact=fund_slug)
            print(f'PayableNetAPIView unit_slug: {unit_slug}')   # TODO JJH remove
            print(f'PayableNetAPIView fund_slug: {fund_slug}')   # TODO JJH remove

            net_summary = accruable_net_summary(bill_qs)
            entity_model = bill_qs.first().ledger.entity
            net_payables = {
                'entity_slug': self.kwargs['entity_slug'],
                'entity_name': entity_model.name,
                'net_payable_data': net_summary
            }

            return JsonResponse({
                'results': net_payables
            })

        return JsonResponse({
            'message': 'Unauthorized'
        }, status=401)


class ReceivableNetAPIView(DjangoLedgerSecurityMixIn, EntityUnitMixIn, FundMixIn, View):
    http_method_names = ['get']

    def get_context_data(self, **kwargs):
        if EntityUnitMixIn.UNIT_SLUG_KWARG in self.kwargs:
            # Call the EntityUnitMixIn's get_context_data() explicitly
            context = EntityUnitMixIn.get_context_data(self, **kwargs)
            print(f'ReceivableNetAPIView using unit dashboard context')   # TODO JJH remove
        elif FundMixIn.FUND_SLUG_KWARG in self.kwargs:
            # Call the FundMixIn's get_context_data() explicitly
            context = FundMixIn.get_context_data(self, **kwargs)
            print(f'ReceivableNetAPIView using fund dashboard context')   # TODO JJH remove
        else:
            # Default behavior if neither match
            context = super().get_context_data(**kwargs)
            print(f'ReceivableNetAPIView using entity dashboard context')   # TODO JJH remove

        return context

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            invoice_qs = InvoiceModel.objects.for_entity(
                entity_slug=self.kwargs['entity_slug'],
                user_model=request.user,
            ).unpaid()

            # todo: implement this...
            unit_slug = self.get_unit_slug()
            # if unit_slug:
            #     invoice_qs.filter(ledger__journal_entry__entity_unit__slug__exact=unit_slug)
            # todo: implement this too...
            fund_slug = self.get_fund_slug()
            # if fund_slug:
            #     invoice_qs.filter(ledger__journal_entry__?__slug__exact=fund_slug)
            print(f'ReceivableNetAPIView unit_slug: {unit_slug}')   # TODO JJH remove
            print(f'ReceivableNetAPIView fund_slug: {fund_slug}')   # TODO JJH remove

            net_summary = accruable_net_summary(invoice_qs)
            entity_model = invoice_qs.first().ledger.entity
            net_receivable = {
                'entity_slug': self.kwargs['entity_slug'],
                'entity_name': entity_model.name,
                'net_receivable_data': net_summary
            }

            return JsonResponse({
                'results': net_receivable
            })

        return JsonResponse({
            'message': 'Unauthorized'
        }, status=401)
