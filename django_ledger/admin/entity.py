from datetime import timedelta
from uuid import uuid4

from django.contrib.admin import TabularInline, ModelAdmin
from django.db.models import Count
from django.forms import BaseInlineFormSet
from django.urls import reverse
from django.utils.html import format_html

from django_ledger.admin.chart_of_accounts import ChartOfAccountsInLine
from django_ledger.io.utils import get_localtime
from django_ledger.models import EntityUnitModel, FundModel
from django_ledger.models.entity import EntityModel, EntityManagementModel
from django_ledger.settings import DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES

class EntityManagementInLine(TabularInline):
    model = EntityManagementModel
    extra = 1
    fields = [
        'user'
    ]


class EntityUnitModelInLineFormSet(BaseInlineFormSet):

    def save_new(self, form, commit=True):
        # noinspection PyUnresolvedReferences
        setattr(form.instance, self.fk.name, self.instance)     # self.fk.name comes from the parent class
        if commit:
            unit_model = EntityUnitModel.add_root(
                instance=super().save_new(form, commit=False)
            )
            return unit_model
        return super().save_new(form, commit=False)


class EntityUnitModelInLine(TabularInline):
    model = EntityUnitModel
    formset = EntityUnitModelInLineFormSet
    extra = 0
    readonly_fields = [
        'slug'
    ]
    fields = [
        'slug',
        'name',
        'document_prefix',
        'active',
        'hidden'
    ]


class FundModelInLineFormSet(BaseInlineFormSet):

    def save_new(self, form, commit=True):
        # noinspection PyUnresolvedReferences
        setattr(form.instance, self.fk.name, self.instance)
        if commit:
            fund_model = FundModel.add_root(
                instance=super().save_new(form, commit=False)
            )
            return fund_model
        return super().save_new(form, commit=False)


class FundModelInLine(TabularInline):
    model = FundModel
    formset = FundModelInLineFormSet
    extra = 0
    readonly_fields = [
        'slug'
    ]
    fields = [
        'slug',
        'name',
        'document_prefix',
        'active',
        'hidden'
    ]


# noinspection PyUnresolvedReferences
class EntityModelAdmin(ModelAdmin):
    list_display = [
        'slug',
        'name',
        'admin',
        'accrual_method',
        'last_closing_date',
        'hidden',
        'get_coa_count',
        'add_ledger_link',
        'dashboard_link',
        'balance_sheet_link',
        'income_statement_link',
        'cash_flow_statement_link'
    ]
    readonly_fields = [
        'depth',
        'path',
        'numchild',
        'last_closing_date',
        'default_coa'
    ]
    fieldsets = [
        (
            'Entity Information', {
                'fields': [
                    'name',
                    'admin',
                    'fy_start_month',
                    'accrual_method',
                    'hidden',
                    'picture'
                ]
            }
        ),
        (
            'Contact Information', {
                'fields': [
                    'address_1',
                    'address_2',
                    'city',
                    'state',
                    'zip_code',
                    'email',
                    'website',
                    'phone'
                ]
            }
        ),
        (
            'Chart of Accounts', {
                'fields': [
                    'default_coa'
                ]
            }
        )
    ]
    inlines = [
        ChartOfAccountsInLine,
        EntityUnitModelInLine,
        EntityManagementInLine
    ]
    if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
        inlines.insert(2, FundModelInLine)      # place after entity unit

    actions = [
        'add_code_of_accounts',
        'populate_random_data'
    ]

    class Meta:
        model = EntityModel

    def get_queryset(self, request):
        qs = super().get_queryset(request=request)
        qs = qs.annotate(Count('chartofaccountmodel'))
        if request.user.is_superuser:
            return qs
        return qs.for_user(user_model=request.user)

    @staticmethod
    def add_ledger_link(obj):
        add_ledger_url = reverse('admin:django_ledger_ledgermodel_add')
        return format_html('<a class="addlink" href="{url}?entity_slug={slug}">Add Ledger</a>',
                           url=add_ledger_url,
                           slug=obj.slug)

    def balance_sheet_link(self, obj: EntityModel):
        add_ledger_url = reverse(
            viewname='django_ledger:entity-bs',
            kwargs={
                'entity_slug': obj.slug
            })
        return format_html('<a class="viewlink" href="{url}">View</a>',
                           url=add_ledger_url,
                           slug=obj.slug)

    balance_sheet_link.short_description = 'Balance Sheet'

    def income_statement_link(self, obj: EntityModel):
        add_ledger_url = reverse(
            viewname='django_ledger:entity-ic',
            kwargs={
                'entity_slug': obj.slug
            })
        return format_html('<a class="viewlink" href="{url}">View</a>',
                           url=add_ledger_url,
                           slug=obj.slug)

    income_statement_link.short_description = 'P&L'

    def cash_flow_statement_link(self, obj: EntityModel):
        add_ledger_url = reverse(
            viewname='django_ledger:entity-cf',
            kwargs={
                'entity_slug': obj.slug
            })
        return format_html('<a class="viewlink" href="{url}">View</a>',
                           url=add_ledger_url,
                           slug=obj.slug)

    cash_flow_statement_link.short_description = 'Cash Flow'

    def dashboard_link(self, obj: EntityModel):
        add_ledger_url = reverse(
            viewname='django_ledger:entity-dashboard',
            kwargs={
                'entity_slug': obj.slug
            })
        return format_html('<a class="viewlink" href="{url}">View</a>',
                           url=add_ledger_url,
                           slug=obj.slug)

    dashboard_link.short_description = 'Dashboard'

    # noinspection PyUnusedLocal
    @staticmethod
    def add_code_of_accounts(request, queryset):
        lt = get_localtime().isoformat()
        for entity_model in queryset:
            entity_model.create_chart_of_accounts(
                coa_name=f'{entity_model.name} CoA {lt}',
                commit=True,
                assign_as_default=False
            )

    # noinspection PyUnusedLocal
    @staticmethod
    def populate_random_data(request, queryset):
        for entity_model in queryset:
            start_date = get_localtime() - timedelta(days=180)
            entity_model.populate_random_data(
                start_date=start_date,
                days_forward=180,
                tx_quantity=25)

    def get_coa_count(self, obj):
        return obj.chartofaccountmodel__count

    get_coa_count.short_description = 'CoA Count'

    def save_model(self, request, obj, form, change):
        if not change:
            if obj.uuid is None:
                obj.uuid = uuid4()
            EntityModel.add_root(instance=obj)
            return
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False
