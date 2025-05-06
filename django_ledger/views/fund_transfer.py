"""
"""

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    UpdateView, CreateView, ArchiveIndexView, MonthArchiveView, YearArchiveView,
    DetailView, RedirectView
)
from django.views.generic.detail import SingleObjectMixin

from django_ledger.forms.fund_transfer import (
    FundTransferModelCreateForm,
    BaseFundTransferModelUpdateForm, FundTransferModelConfigureForm,
)
from django_ledger.io.utils import get_localdate
from django_ledger.models import EntityModel
from django_ledger.models.fund_transfer import FundTransferModel, FundTransferModelQuerySet
from django_ledger.views.mixins import DjangoLedgerSecurityMixIn


class FundTransferModelModelBaseView(DjangoLedgerSecurityMixIn):
    queryset = None

    # noinspection PyUnresolvedReferences
    def get_queryset(self):
        if self.queryset is None:
            entity_model: EntityModel = self.get_authorized_entity_instance()
            qs: FundTransferModelQuerySet = entity_model.get_fund_transfers()
            self.queryset = qs
        return super().get_queryset()


class FundTransferModelCreateView(FundTransferModelModelBaseView, CreateView):
    template_name = 'django_ledger/fund_transfers/fund_transfer_create.html'
    PAGE_TITLE = _('Create Fund Transfer')
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        'header_subtitle_icon': 'uil:fund_transfer'
    }

    def get(self, request, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        return super(FundTransferModelCreateView, self).get(request, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(FundTransferModelCreateView, self).get_context_data(**kwargs)
        form_action = reverse('django_ledger:fund-transfer-create',
                              kwargs={
                                  'entity_slug': self.kwargs['entity_slug'],
                              })
        context['form_action_url'] = form_action
        return context

    def get_initial(self):
        return {
            'transfer_date': get_localdate()
        }

    def get_form(self, form_class=None):
        entity_model: EntityModel = self.get_authorized_entity_instance()
        return FundTransferModelCreateForm(
            entity_model=entity_model,
            **self.get_form_kwargs()
        )

    def form_valid(self, form):
        fund_transfer_model: FundTransferModel = form.save(commit=False)
        fund_transfer_model.configure(
            entity_slug=self.AUTHORIZED_ENTITY_MODEL,
            commit_ledger=True
        )
        return super(FundTransferModelCreateView, self).form_valid(form)

    def get_success_url(self):
        entity_slug = self.kwargs['entity_slug']
        fund_transfer_model: FundTransferModel = self.object
        return reverse('django_ledger:fund-transfer-detail',
                       kwargs={
                           'entity_slug': entity_slug,
                           'fund_transfer_pk': fund_transfer_model.uuid
                       })


class FundTransferModelListView(FundTransferModelModelBaseView, ArchiveIndexView):
    template_name = 'django_ledger/fund_transfers/fund_transfer_list.html'
    context_object_name = 'fund_transfers'
    PAGE_TITLE = _('Fund Transfer List')

    # todo: can this be status date?...
    date_field = 'transfer_date'
    paginate_by = 20
    paginate_orphans = 2
    allow_empty = True
    ordering = '-updated'
    extra_context = {
        'page_title': PAGE_TITLE,
        'header_title': PAGE_TITLE,
        'header_subtitle_icon': 'uil:fund_transfer'
    }


class FundTransferModelYearListView(YearArchiveView, FundTransferModelListView):
    paginate_by = 20
    make_object_list = True


class FundTransferModelMonthListView(MonthArchiveView, FundTransferModelListView):
    paginate_by = 20
    month_format = '%m'
    date_list_period = 'year'


class FundTransferModelDetailView(FundTransferModelModelBaseView, DetailView):
    slug_url_kwarg = 'fund_transfer_pk'
    slug_field = 'uuid'
    context_object_name = 'fund_transfer_model'
    template_name = 'django_ledger/fund_transfers/fund_transfer_detail.html'
    extra_context = {
        'header_subtitle_icon': 'uil:fund_transfer'
    }
    http_method_names = ['get']
    action_update_items = False

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        fund_transfer_model: FundTransferModel = self.object
        title = f'Fund Transfer {fund_transfer_model.fund_transfer_number}'
        context['page_title'] = title
        context['header_title'] = title

        fund_transfer_model: FundTransferModel = self.object

        if not fund_transfer_model.is_configured():
            link = format_html(f"""
            <a href="{reverse("django_ledger:fund-transfer-update", kwargs={
                'entity_slug': self.kwargs['entity_slug'],
                'fund_transfer_pk': fund_transfer_model.uuid
            })}">here</a>
            """)
            msg = f'Fund Transfer {fund_transfer_model.fund_transfer_number} has not been fully set up. ' + \
                  f'Please update or assign associated accounts {link}.'
            messages.add_message(self.request,
                                 message=msg,
                                 level=messages.WARNING,
                                 extra_tags='is-danger')
        return context

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related(
            'ledger',
            'ledger__entity',
            'from_fund',
            'from_account',
            'to_fund',
            'to_account',
        )


class FundTransferModelUpdateView(FundTransferModelModelBaseView, UpdateView):
    slug_url_kwarg = 'fund_transfer_pk'
    slug_field = 'uuid'
    context_object_name = 'fund_transfer_model'
    template_name = 'django_ledger/fund_transfers/fund_transfer_update.html'
    extra_context = {
        'header_subtitle_icon': 'uil:fund_transfer'
    }
    http_method_names = ['get', 'post']
    action_update_items = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object = None

    def get_form(self, form_class=None):
        form_class = self.get_form_class()
        entity_model: EntityModel = self.get_authorized_entity_instance()
        if self.request.method == 'POST' and self.action_update_items:
            return form_class(
                entity_model=entity_model,
                user_model=self.request.user,
                instance=self.object
            )
        return form_class(
            entity_model=entity_model,
            user_model=self.request.user,
            **self.get_form_kwargs()
        )

    def get_form_class(self):
        fund_transfer_model: FundTransferModel = self.object
        if not fund_transfer_model.is_configured():
            return FundTransferModelConfigureForm
        return BaseFundTransferModelUpdateForm

    def get_context_data(self,
                         *,
                         object_list=None,
                         **kwargs):

        context = super().get_context_data(object_list=object_list, **kwargs)
        entity_model: EntityModel = self.get_authorized_entity_instance()
        fund_transfer_model: FundTransferModel = self.object
        ledger_model = fund_transfer_model.ledger

        title = f'Fund Transfer {fund_transfer_model.fund_transfer_number}'
        context['page_title'] = title
        context['header_title'] = title

        if not fund_transfer_model.is_configured():
            messages.add_message(
                request=self.request,
                message=f'Fund Transfer {fund_transfer_model.fund_transfer_number} must have all accounts configured.',
                level=messages.ERROR,
                extra_tags='is-danger'
            )

        if ledger_model.locked:
            messages.add_message(self.request,
                                 messages.ERROR,
                                 f'Warning! This fund transfer is locked. Must unlock before making any changes.',
                                 extra_tags='is-danger')

        if not ledger_model.is_posted():
            messages.add_message(self.request,
                                 messages.INFO,
                                 f'This fund transfer has not been posted. Must post to see ledger changes.',
                                 extra_tags='is-info')

        return context

    def get_success_url(self):
        entity_slug = self.kwargs['entity_slug']
        fund_transfer_pk = self.kwargs['fund_transfer_pk']
        return reverse('django_ledger:fund_transfer-detail',
                       kwargs={
                           'entity_slug': entity_slug,
                           'fund_transfer_pk': fund_transfer_pk
                       })

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related(
            'ledger',
            'ledger__entity',
            'from_fund',
            'from_account',
            'to_fund',
            'to_account',
        )

    def form_valid(self, form):
        form.save(commit=False)
        messages.add_message(self.request,
                             messages.SUCCESS,
                             f'Fund Transfer {self.object.fund_transfer_number} successfully updated.',
                             extra_tags='is-success')
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        if self.action_update_items:
            return HttpResponseRedirect(
                redirect_to=reverse('django_ledger:fund_transfer-update',
                                    kwargs={
                                        'entity_slug': self.kwargs['entity_slug'],
                                        'fund_transfer_pk': self.kwargs['fund_transfer_pk']
                                    })
            )
        return super(FundTransferModelUpdateView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.action_update_items:

            if not request.user.is_authenticated:
                return HttpResponseForbidden()

            queryset = self.get_queryset()
            entity_model: EntityModel = self.get_authorized_entity_instance()
            fund_transfer_model: FundTransferModel = self.get_object(queryset=queryset)
            fund_transfer_pk = fund_transfer_model.uuid

            self.object = fund_transfer_model
            context = self.get_context_data()
            return self.render_to_response(context=context)
        return super(FundTransferModelUpdateView, self).post(request, **kwargs)


# ACTION VIEWS...
class BaseFundTransferActionView(FundTransferModelModelBaseView, RedirectView, SingleObjectMixin):
    http_method_names = ['get']
    pk_url_kwarg = 'fund_transfer_pk'
    action_name = None
    commit = True

    def get_redirect_url(self, *args, **kwargs):
        return reverse('django_ledger:fund-transfer-detail',
                       kwargs={
                           'entity_slug': kwargs['entity_slug'],
                           'fund_transfer_pk': kwargs['fund_transfer_pk']
                       })

    def get(self, request, *args, **kwargs):
        kwargs['user_model'] = self.request.user
        if not self.action_name:
            raise ImproperlyConfigured('View attribute action_name is required.')
        response = super(BaseFundTransferActionView, self).get(request, *args, **kwargs)
        fund_transfer_model: FundTransferModel = self.get_object()

        try:
            getattr(fund_transfer_model, self.action_name)(commit=self.commit, **kwargs)
        except ValidationError as e:
            messages.add_message(request,
                                 message=e.message,
                                 level=messages.ERROR,
                                 extra_tags='is-danger')
        return response


class FundTransferModelActionVoidView(BaseFundTransferActionView):
    action_name = 'mark_as_void'


class FundTransferModelActionLockLedgerView(BaseFundTransferActionView):
    action_name = 'lock_ledger'


class FundTransferModelActionUnlockLedgerView(BaseFundTransferActionView):
    action_name = 'unlock_ledger'

    def get_redirect_url(self, entity_slug, fund_transfer_pk, *args, **kwargs):
        return reverse('django_ledger:fund-transfer-update',
                       kwargs={
                           'entity_slug': entity_slug,
                           'fund_transfer_pk': fund_transfer_pk
                       })
