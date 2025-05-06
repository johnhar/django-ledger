from django.forms import (ModelForm, DateInput, TextInput, Select,
                          Textarea)
from django.utils.translation import gettext_lazy as _

from django_ledger.io.roles import ASSET_CA_CASH
from django_ledger.models import FundTransferModel, EntityModel
from django_ledger.settings import DJANGO_LEDGER_FORM_INPUT_CLASSES


class FundTransferModelCreateForm(ModelForm):
    def __init__(self, *args, entity_model: EntityModel, **kwargs):
        super().__init__(*args, **kwargs)
        self.ENTITY_MODEL = entity_model
        self.get_accounts_queryset()

    def get_funds_queryset(self):
        if all([
            'from_fund' in self.fields,
            'to_fund' in self.fields,
        ]):
            fund_qs = self.ENTITY_MODEL.fundmodel_set.all()
            self.fields['from_fund'].queryset = fund_qs
            self.fields['to_fund'].queryset = fund_qs

    def get_accounts_queryset(self):
        if all([
            'from_account' in self.fields,
            'to_account' in self.fields,
        ]):
            account_qs = self.ENTITY_MODEL.default_coa.accountmodel_set.all().for_fund_transfer()
            self.fields['from_account'].queryset = account_qs.filter(role__exact=ASSET_CA_CASH)
            self.fields['to_account'].queryset = account_qs.filter(role__exact=ASSET_CA_CASH)

    class Meta:
        model = FundTransferModel
        fields = [
            'transfer_date',
            'from_fund',
            'from_account',
            'to_fund',
            'to_account',
            'amount',
            'markdown_notes',
        ]
        labels = {
        }
        widgets = {
            'transfer_date': DateInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Transfer Date (YYYY-MM-DD)...'),
                'id': 'djl-fund-transfer-date-input'
            }),
            'amount': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': '$$$',
                'id': 'djl-fund-transfer-amount-input'}),
            'from_fund': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'id': 'djl-fund-transfer-from-fund-input'
            }),
            'from_account': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'id': 'djl-fund-transfer-from-account-input'
            }),
            'to_fund': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'id': 'djl-fund-transfer-to-fund-input'
            }),
            'to_account': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'id': 'djl-fund-transfer-to-account-input'
            }),
        }


class BaseFundTransferModelUpdateForm(FundTransferModelCreateForm):
    def __init__(self,
                 *args,
                 entity_model,
                 user_model,
                 **kwargs):
        super().__init__(entity_model=entity_model, *args, **kwargs)
        self.ENTITY_MODEL = entity_model
        self.USER_MODEL = user_model
        self.FUND_TRANSFER_MODEL: FundTransferModel = self.instance

    class Meta:
        model = FundTransferModel
        fields = [
            'markdown_notes'
        ]
        widgets = {
            'amount': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': '$$$'
            }),
            'transfer_date': DateInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Transfer Date (YYYY-MM-DD)...')
            }),
            'from_fund': Select(attrs={'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-danger'}),
            'from_account': Select(attrs={'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-danger'}),
            'to_fund': Select(attrs={'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-danger'}),
            'to_account': Select(attrs={'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-danger'}),
            'markdown_notes': Textarea(attrs={
                'class': 'textarea'
            }),
        }
        labels = {
            'markdown_notes': _('Notes')
        }


class FundTransferModelConfigureForm(BaseFundTransferModelUpdateForm):
    class Meta(BaseFundTransferModelUpdateForm.Meta):
        fields = [
            'transfer_date',
            'from_fund',
            'from_account',
            'to_fund',
            'to_account',
            'amount',
            'markdown_notes',
        ]
