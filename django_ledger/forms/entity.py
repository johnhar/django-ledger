"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

Contributions to this module:
Miguel Sanda <msanda@arrobalytics.com>
"""

from django.forms import (ModelForm, TextInput, BooleanField, ValidationError, EmailInput, URLInput, CheckboxInput,
                          Select)
from django.utils.translation import gettext_lazy as _

from django_ledger.forms.utils import validate_cszc
from django_ledger.models.entity import EntityModel
from django_ledger.settings import DJANGO_LEDGER_FORM_INPUT_CLASSES, DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES


class EntityModelCreateForm(ModelForm):
    if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
        default_funds = BooleanField(required=False, initial=False, label=_('Populate Default Funds (if entity is a nonprofit)'))
        activate_all_funds = BooleanField(required=False, initial=False, label=_('Activate All Funds (if entity is a nonprofit)'))
    default_coa = BooleanField(required=False, initial=False, label=_('Populate Default CoA'))
    activate_all_accounts = BooleanField(required=False, initial=False, label=_('Activate All Accounts'))
    generate_sample_data = BooleanField(required=False, initial=False, label=_('Fill With Sample Data?'))

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError(_('Please provide a valid name for new Entity.'))
        if len(name) < 3:
            raise ValidationError(_('Looks like this entity name is too short...'))
        return name

    def clean(self):
        populate_coa = self.cleaned_data['default_coa']
        activate_all_accounts = self.cleaned_data['activate_all_accounts']
        sample_data = self.cleaned_data['generate_sample_data']

        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
            is_nonprofit = self.cleaned_data.get('is_nonprofit', False)
            populate_funds = self.cleaned_data.get('default_funds', False)
            activate_all_funds = self.cleaned_data.get('activate_all_funds', False)
            if sample_data and not all([
                populate_funds if is_nonprofit else True,
                activate_all_funds if is_nonprofit else True,
                populate_coa,
                activate_all_accounts,
            ]):
                raise ValidationError(f'Filling sample data requires using default funds, default CoA and activate all funds and accounts.')
        else:
            if sample_data and not all([
                populate_coa,
                activate_all_accounts,
            ]):
                raise ValidationError(f'Filling sample data requires using default CoA and activate all accounts.')

        validate_cszc(self.cleaned_data)

    class Meta:
        model = EntityModel
        fields = [
            'name',
            'address_1',
            'address_2',
            'city',
            'state',
            'zip_code',
            'country',
            'email',
            'website',
            'phone',
            'fy_start_month',
            'activate_all_accounts',
            'accrual_method'
        ]
        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
            # insert fund-specific fields between 'fy_start_month' and 'activate_all_accounts'
            fields.insert(11, 'is_nonprofit')
            fields.insert(12, 'activate_all_funds')
            fields.insert(13, 'default_funds')

        labels = {
            'name': _('Entity Name'),
        }
        widgets = {
            'name': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES + ' is-large',
                    'placeholder': _('Entity name...'),
                    'required': True
                }
            ),
            'address_1': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Address line 1')
            }),
            'address_2': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Address line 2')
            }),
            'city': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('City')
            }),
            'state': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('State')
            }),
            'zip_code': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Zip Code')
            }),
            'country': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Country')
            }),
            'phone': TextInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Phone number...')
            }),
            'email': EmailInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('Entity email...')
            }),
            'website': URLInput(attrs={
                'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                'placeholder': _('https://www.mywebsite.com...')
            }),
            'default_coa': CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'fy_start_month': Select(attrs={
                'class': 'input'
            }),
            'accrual_method': CheckboxInput(attrs={
                'class': 'checkbook'
            })
        }
        if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
            widgets['is_nonprofit'] = CheckboxInput(attrs={ 'class': 'checkbox' })
            widgets['default_funds'] = CheckboxInput(attrs={ 'class': 'checkbox' })


class EntityModelUpdateForm(ModelForm):
    class Meta:
        model = EntityModel
        fields = [
            'name',
            'address_1',
            'address_2',
            'city',
            'state',
            'zip_code',
            'country',
            'email',
            'phone',
            'website',
            'fy_start_month'
        ]
        labels = {
            'name': _('Entity Name')
        }
        widgets = {
            'name': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Entity name...')
                }
            ),
            'address_1': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Address line 1')
                }),
            'address_2': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Address line 2')
                }),
            'city': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('City')
                }),
            'state': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('State')
                }),
            'zip_code': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Zip Code')
                }),
            'country': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Country')
                }),
            'email': EmailInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Email...')
                }
            ),
            'phone': TextInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Phone...')
                }
            ),
            'website': URLInput(
                attrs={
                    'class': DJANGO_LEDGER_FORM_INPUT_CLASSES,
                    'placeholder': _('Website...')
                }
            ),
            'fy_start_month': Select(
                attrs={
                    'class': 'input'
                })
        }
