"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

Contributions to this module:
    - Miguel Sanda <msanda@arrobalytics.com>
    - Michael Noel <noel.michael87@gmail.com>
"""

from django.forms import ModelForm, modelformset_factory, BaseModelFormSet, TextInput, Select, ValidationError
from django.utils.translation import gettext_lazy as _

from django_ledger.io.utils import check_tx_balance
from django_ledger.models import EntityModel
from django_ledger.models.journal_entry import JournalEntryModel
from django_ledger.models.transactions import TransactionModel
from django_ledger.settings import DJANGO_LEDGER_FORM_INPUT_CLASSES, DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES


class TransactionModelForm(ModelForm):
    class Meta:
        model = TransactionModel
        fields = [
            'account',
            'tx_type',
            'amount',
            'description'
        ]
        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
            fields.append('fund')

        widgets = {
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

        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
            widgets['fund'] = Select(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-small',
            })


class TransactionModelFormSet(BaseModelFormSet):

    def __init__(self, *args, entity_model: EntityModel, je_model: JournalEntryModel, **kwargs):
        super().__init__(*args, **kwargs)
        je_model.validate_for_entity(entity_model)
        self.JE_MODEL: JournalEntryModel = je_model
        self.ENTITY_MODEL = entity_model

        account_qs = self.ENTITY_MODEL.get_coa_accounts().active().order_by('code')

        for form in self.forms:
            form.fields['account'].queryset = account_qs

            # Handle fund field if nonprofit features are enabled
            if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES and 'fund' in form.fields:
                # Get all funds for the entity
                fund_qs = self.ENTITY_MODEL.fundmodel_set.all().order_by('name')
                form.fields['fund'].queryset = fund_qs

                # For fund transfers, set the appropriate fund based on transaction type
                if self.JE_MODEL.is_fund_transfer():
                    # For new forms (no instance), pre-set the fund based on tx_type
                    if not form.instance.pk and 'tx_type' in form.data:
                        tx_type = form.data.get(f'{form.prefix}-tx_type')
                        if tx_type == 'credit':
                            form.fields['fund'].initial = self.JE_MODEL.fund_id
                        elif tx_type == 'debit':
                            form.fields['fund'].initial = self.JE_MODEL.receiving_fund_id
                # For regular journal entries, set the fund to the journal entry's fund
                else:
                    form.fields['fund'].initial = self.JE_MODEL.fund_id

            if self.JE_MODEL.is_locked():
                form.fields['account'].disabled = True
                form.fields['tx_type'].disabled = True
                form.fields['amount'].disabled = True
                if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES and 'fund' in form.fields:
                    form.fields['fund'].disabled = True

    def get_queryset(self):
        return self.JE_MODEL.transactionmodel_set.all()

    def clean(self):
        # Skip validation if there are errors in forms
        if any(self.errors):
            return
        for form in self.forms:
            # noinspection PyUnresolvedReferences
            if self.can_delete and self._should_delete_form(form):
                continue

            # Skip empty forms
            if all(not bool(value) for value in form.cleaned_data.values()):
                continue

        # Validate transaction balance
        txs_balances = [{
            'tx_type': tx.cleaned_data.get('tx_type'),
            'amount': tx.cleaned_data.get('amount')
        } for tx in self.forms if not self._should_delete_form(tx)]
        balance_ok = check_tx_balance(txs_balances, perform_correction=False)
        if not balance_ok:
            raise ValidationError(message=_('Credits and Debits do not balance.'))

        # Validate fund values for fund transfers
        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES and self.JE_MODEL.is_fund_transfer():
            valid_forms = [form for form in self.forms if not self._should_delete_form(form) and 
                          not all(not bool(value) for value in form.cleaned_data.values())]

            if len(valid_forms) == 2:
                # Get credit and debit transactions
                credit_form = next((form for form in valid_forms if form.cleaned_data.get('tx_type') == 'credit'), None)
                debit_form = next((form for form in valid_forms if form.cleaned_data.get('tx_type') == 'debit'), None)

                if credit_form and debit_form:
                    # Check that credit transaction has source fund and debit transaction has receiving fund
                    if credit_form.cleaned_data.get('fund') != self.JE_MODEL.fund:
                        raise ValidationError(message=_('Credit transaction must use the source fund.'))
                    if debit_form.cleaned_data.get('fund') != self.JE_MODEL.receiving_fund:
                        raise ValidationError(message=_('Debit transaction must use the receiving fund.'))


def get_transactionmodel_formset_class(journal_entry_model: JournalEntryModel):
    can_delete = not journal_entry_model.is_locked()
    return modelformset_factory(
        model=TransactionModel,
        form=TransactionModelForm,
        formset=TransactionModelFormSet,
        can_delete=can_delete,
        extra=6 if can_delete else 0)
