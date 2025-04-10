"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

Contributions to this module:
    - Miguel Sanda <msanda@arrobalytics.com>
    - Michael Noel <noel.michael87@gmail.com>
"""

from django.forms import ModelForm, modelformset_factory, BaseModelFormSet, TextInput, Select, ValidationError
from django.utils.translation import gettext_lazy as _

from django_ledger.io.io_core import check_tx_balance
from django_ledger.models import EntityModel, FundModel
from django_ledger.models.journal_entry import JournalEntryModel
from django_ledger.models.transactions import TransactionModel
from django_ledger.settings import DJANGO_LEDGER_FORM_INPUT_CLASSES


class TransactionModelForm(ModelForm):
    class Meta:
        model = TransactionModel
        fields = [
            'fund',
            'account',
            'tx_type',
            'amount',
            'description'
        ]
        widgets = {
            'fund': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            }),
            'account': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            }),
            'tx_type': Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            }),
            'amount': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            }),
            'description': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            }),
        }

    def __init__(self, *args, is_fund_enabled=False, **kwargs):
        """Initialize the form and control the 'fund' field based on 'is_fund_enabled'."""
        super().__init__(*args, **kwargs)

        # Dynamically disable fund field if it's not used
        self.fields['fund'].required = True if is_fund_enabled else False
        self.fields['fund'].disabled = True if is_fund_enabled else False


class TransactionModelFormSet(BaseModelFormSet):

    def __init__(self, *args, entity_model: EntityModel, je_model: JournalEntryModel, **kwargs):
        super().__init__(*args, **kwargs)
        je_model.validate_for_entity(entity_model)
        self.JE_MODEL: JournalEntryModel = je_model
        self.ENTITY_MODEL = entity_model
        is_fund_enabled = self.ENTITY_MODEL.is_fund_enabled()

        account_qs = self.ENTITY_MODEL.get_coa_accounts().active().order_by('code')
        fund_qs = FundModel.objects.filter(entity=self.ENTITY_MODEL).active().order_by(
            'document_prefix') if is_fund_enabled else None

        for form in self.forms:
            form.fields['account'].queryset = account_qs

            if is_fund_enabled:
                form.fields['fund'].queryset = fund_qs
                form.fields['fund'].required = True
                form.fields['fund'].disabled = False
            else:
                form.fields['fund'].required = False
                form.fields['fund'].disabled = True

            if self.JE_MODEL.is_locked():
                form.fields['fund'].disabled = True
                form.fields['account'].disabled = True
                form.fields['tx_type'].disabled = True
                form.fields['amount'].disabled = True

    def get_queryset(self):
        return self.JE_MODEL.transactionmodel_set.all()

    def clean(self):
        # Skip validation if there are errors in forms
        if any(self.errors):
            return
        for form in self.forms:
            # Skip forms marked for deletion
            if self.can_delete and self._should_delete_form(form):
                continue

            # Skip empty forms
            if all(not bool(value) for value in form.cleaned_data.values()):
                continue

            # Validate 'fund' field only if is_fund_enabled is True
            if form.fields['fund'].required:
                fund = form.cleaned_data.get('fund')
                if not fund:
                    form.add_error('fund', _('This field is required for non-profit.'))

        # Validate transaction balance
        txs_balances = [{
            'tx_type': tx.cleaned_data.get('tx_type'),
            'amount': tx.cleaned_data.get('amount')
        } for tx in self.forms if not self._should_delete_form(tx)]
        balance_ok = check_tx_balance(txs_balances, perform_correction=False)
        if not balance_ok:
            raise ValidationError(message=_('Credits and Debits do not balance.'))


def get_transactionmodel_formset_class(journal_entry_model: JournalEntryModel):
    can_delete = not journal_entry_model.is_locked()
    return modelformset_factory(
        model=TransactionModel,
        form=TransactionModelForm,
        formset=TransactionModelFormSet,
        can_delete=can_delete,
        extra=6 if can_delete else 0)
