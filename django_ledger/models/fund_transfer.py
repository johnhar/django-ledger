"""
This model implements the FundTransferModel, representing a fund transfer for a nonprofit entity.
Fund transfers are transfers of assets from one fund to another.

"""
from datetime import date, datetime
from decimal import Decimal
from typing import Union, Optional, Dict
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import models, transaction, IntegrityError
from django.db.models import QuerySet, Manager, Q, F
from django.db.models.signals import pre_save
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from django_ledger.io.utils import get_localdate, validate_io_timestamp, get_localtime
from django_ledger.models import lazy_loader
from django_ledger.models.entity import EntityModel, EntityStateModel, EntityStateModelAbstract
from django_ledger.models.mixins import ( CreateUpdateMixIn, MarkdownNotesMixIn, )
from django_ledger.models.signals import fund_transfer_status_void
from django_ledger.settings import DJANGO_LEDGER_DOCUMENT_NUMBER_PADDING, DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES, \
    DJANGO_LEDGER_FUND_TRANSFER_NUMBER_PREFIX

UserModel = get_user_model()


class FundTransferModelValidationError(ValidationError):
    pass


class FundTransferModelQuerySet(QuerySet):
    pass


class FundTransferModelManager(Manager):
    """
    A custom defined FundTransferModelManager that will act as an interface to handling the initial DB queries
    to the FundTransferModel. The default "get_queryset" has been overridden to refer the custom defined
    "FundTransferModelQuerySet".
    """

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related(
            'ledger',
            'ledger__entity'
        )

    def for_user(self, user_model) -> FundTransferModelQuerySet:
        """
        Fetches a QuerySet of FundTransferModels that the UserModel as access to.
        May include FundTransferModels from multiple Entities.

        The user has access to fund transfers if:
            1. Is listed as Manager of Entity.
            2. Is the Admin of the Entity.

        Parameters
        __________
        user_model
            Logged in and authenticated django UserModel instance.

        Examples
        ________
                request_user = request.user
                fund_transfer_model_qs = FundTransferModel.objects.for_user(user_model=request_user)

        Returns
        _______
        FundTransferModelQuerySet
            Returns a FundTransferModelQuerySet with applied filters.
        """
        qs = self.get_queryset()
        if user_model.is_superuser:
            return qs
        return qs.filter(
            Q(ledger__entity__admin=user_model) |
            Q(ledger__entity__managers__in=[user_model])
        )

    def for_entity(self, entity_slug, user_model) -> FundTransferModelQuerySet:
        """
        Fetches a QuerySet of FundTransferModels associated with a specific EntityModel & UserModel.
        May pass an instance of EntityModel or a String representing the EntityModel slug.

        Parameters
        ----------
        entity_slug: str or EntityModel
            The entity slug or EntityModel used for filtering the QuerySet.
        user_model
            Logged in and authenticated django UserModel instance.

        Examples
        --------
            request_user = request.user
            slug = kwargs['entity_slug'] # may come from request kwargs
            fund_transfer_model_qs = FundTransferModel.objects.for_entity(user_model=request_user, entity_slug=slug)

        Returns
        -------
        FundTransferModelQuerySet
            Returns a FundTransferModelQuerySet with applied filters.
        """
        qs = self.for_user(user_model)
        if isinstance(entity_slug, EntityModel):
            qs = qs.filter(Q(ledger__entity=entity_slug))
        elif isinstance(entity_slug, str):
            qs = qs.filter(Q(ledger__entity__slug=entity_slug))
        else:
            raise TypeError('entity_slug must be a string or EntityModel')
        # noinspection PyTypeChecker
        return qs


class FundTransferModelAbstract(
    MarkdownNotesMixIn,
    CreateUpdateMixIn
):
    """
       This is the main abstract class which the FundTransferModel database will inherit from.
       The FundTransferModel inherits functionality from the following MixIns:

           1. :func:`AccruralMixIn <django_ledger.models.mixins.AccruralMixIn>`>`
           2. :func:`MarkdownNotesMixIn <django_ledger.models.mixins.MarkdownNotesMixIn>`
           3. :func:`CreateUpdateMixIn <django_ledger.models.mixins.CreateUpdateMixIn>`

       Attributes
       ----------
       uuid : UUID
           This is a unique primary key generated for the table. The default value of this field is uuid4().

       fund_transfer_number: str
           Auto assigned number at creation by generate_fund_transfer_number() function.
           Includes a reference to the Fiscal Year and a sequence number. Max Length is 20.

       additional_info: dict
           Any additional metadata about the FundTransferModel may be stored here as a dictionary object.
           The data is serialized and stored as a JSON document in the Database.
       """
    REL_NAME_PREFIX = 'fund_transfer'

    FUND_TRANSFER_STATUS_CREATED = 'created'
    FUND_TRANSFER_STATUS_VOID = 'void'

    FUND_TRANSFER_STATUS = [
        (FUND_TRANSFER_STATUS_CREATED, _('created')),
        (FUND_TRANSFER_STATUS_VOID, _('Void')),
    ]
    TX_TYPE_MAPPING = {
        'ci': 'credit',
        'dd': 'credit',
        'cd': 'debit',
        'di': 'debit',
    }

    """
    The different fund transfer status options and their representation in the Database.
    """

    uuid = models.UUIDField(default=uuid4, primary_key=True, editable=False)
    fund_transfer_number = models.SlugField(max_length=20, verbose_name='Fund Transfer Number', editable=False)
    fund_transfer_status = models.CharField(max_length=10,
                                            choices=FUND_TRANSFER_STATUS,
                                            default=FUND_TRANSFER_STATUS[0][0],
                                            verbose_name=_('Fund Transfer Status'))
    transfer_date = models.DateField(verbose_name=_('Transfer Date'), help_text=_('Date of the Fund Transfer.'))
    from_fund = models.ForeignKey(
        to='django_ledger.FundModel',
        verbose_name=_('Source Fund'),
        help_text=_('Fund from which the transfer is made.'),
        related_name='fund_transfer_from_fund',
        on_delete=models.RESTRICT,
    )
    from_account = models.ForeignKey(
        to='django_ledger.AccountModel',
        verbose_name=_('Source Account'),
        help_text=_('Account from which the transfer is made.'),
        related_name='fund_transfer_from_account',
        on_delete=models.RESTRICT,
    )
    to_fund = models.ForeignKey(
        to='django_ledger.FundModel',
        verbose_name=_('Destination Fund'),
        help_text=_('Fund to which the transfer is made.'),
        related_name='fund_transfer_to_fund',
        on_delete=models.RESTRICT,
    )
    to_account = models.ForeignKey(
        to='django_ledger.AccountModel',
        verbose_name=_('Destination Account'),
        help_text=_('Account to which the transfer is made.'),
        related_name='fund_transfer_to_account',
        on_delete=models.RESTRICT,
    )
    amount = models.DecimalField(
        default=0,
        max_digits=20,
        decimal_places=2,
    )
    additional_info = models.JSONField(blank=True,
                                       null=True,
                                       default=dict,
                                       verbose_name=_('Fund Transfer Additional Info'))
    # todo: rename to ledger_model...
    ledger = models.OneToOneField('django_ledger.LedgerModel',
                                  editable=False,
                                  verbose_name=_('Ledger'),
                                  on_delete=models.CASCADE)
    date_void = models.DateField(null=True, blank=True, verbose_name=_('Void Date'))

    class Meta:
        abstract = True
        ordering = ['-updated']
        verbose_name = _('Fund Transfer')
        verbose_name_plural = _('Fund Transfers')
        indexes = [
            models.Index(fields=['fund_transfer_number']),
            models.Index(fields=['fund_transfer_status']),
            models.Index(fields=['transfer_date']),
            models.Index(fields=['from_fund']),
            models.Index(fields=['to_fund'])
        ]

    def __str__(self):
        return f'Fund Transfer: {self.fund_transfer_number}'

    def is_configured(self) -> bool:
        return all([
            self.ledger_id,
        ])

    def configure(self,
                  entity_slug: Union[str, EntityModel],
                  user_model: Optional[UserModel] = None,
                  ledger_posted: bool = False,
                  ledger_name: str = None,
                  commit: bool = False,
                  commit_ledger: bool = False):
        """
        A configuration hook which executes all initial FundTransferModel setup on to the LedgerModel and all initial
        values of the FundTransferModel. Can only call this method once in the lifetime of a FundTransferModel.

        Parameters
        ----------

        entity_slug: str or EntityModel
            The entity slug or EntityModel to associate the Fund Transfer with.
        user_model: UserModel
            The UserModel making the request to check for QuerySet permissions.
        ledger_posted: bool
            An option to mark the FundTransferModel Ledger as posted at the time of configuration. Defaults to False.
        ledger_name: str
            Optional additional FundTransferModel ledger name or description.
        commit: bool
            Saves the current FundTransferModel after being configured.
        commit_ledger: bool
            Saves the FundTransferModel's LedgerModel while being configured.

        Returns
        -------
        A tuple of LedgerModel, FundTransferModel
        """
        if not self.is_configured():
            if isinstance(entity_slug, str):
                if not user_model:
                    raise FundTransferModelValidationError(_('Must pass user_model when using entity_slug.'))
                entity_qs = EntityModel.objects.for_user(user_model=user_model)
                entity_model: EntityModel = get_object_or_404(entity_qs, slug__exact=entity_slug)
            elif isinstance(entity_slug, EntityModel):
                entity_model = entity_slug
            else:
                raise FundTransferModelValidationError('entity_slug must be an instance of str or EntityModel')

            self.fund_transfer_status = self.FUND_TRANSFER_STATUS_CREATED

            LedgerModel = lazy_loader.get_ledger_model()
            ledger_model: LedgerModel = LedgerModel(entity=entity_model, posted=ledger_posted)
            ledger_name = f'Fund Transfer {self.uuid}' if not ledger_name else ledger_name
            ledger_model.name = ledger_name
            ledger_model.configure_for_wrapper_model(model_instance=self)
            ledger_model.clean()
            ledger_model.clean_fields()
            self.ledger = ledger_model

            if commit_ledger or commit:
                self.ledger.save()

            if self.can_generate_fund_transfer_number():
                self.generate_fund_transfer_number(commit=commit)
                ledger_model.ledger_xid = f'fund_transfer-{self.fund_transfer_number.lower()}-{str(ledger_model.entity_id)[-5:]}'
                ledger_model.save(update_fields=['ledger_xid'])

            self.clean()

            if commit:
                self.save()

        return self.ledger, self

    def can_migrate(self) -> bool:
        """
        Determines if the Fund Transfer can be migrated to the books.
        Results in additional Database query if 'ledger' field is not pre-fetch on QuerySet.

        Returns
        -------
        bool
            True if can migrate, else False.
        """
        if not self.ledger_id:
            return False
        je = self.ledger.journal_entries.first()
        return not all([
            self.ledger.is_posted(),
            self.ledger.is_locked(),
            je.is_locked() if je else True,
            je.is_posted() if je else True,
        ])

    def can_delete(self) -> bool:
        return any([
            self.is_configured(),
            not self.ledger.is_locked(),
        ])

    def can_void(self) -> bool:
        return all([
            float(self.amount) != 0.0,
            self.is_configured(),
        ])

    def can_generate_fund_transfer_number(self) -> bool:
        return all([
            not self.fund_transfer_number,
            self.is_configured(),
        ])

    def _get_next_state_model(self, raise_exception: bool = True) -> Union[EntityStateModel | None]:
        """
        Fetches the next sequenced state model associated with the FundTransferModel number.

        Parameters
        ----------
        raise_exception: bool
            Raises IntegrityError if unable to secure transaction from DB.

        Returns
        -------
        EntityStateModel
            An instance of EntityStateModel, if no exception is raised.
        """
        _EntityStateModel: type[EntityStateModelAbstract] = lazy_loader.get_entity_state_model()
        _EntityModel: EntityModel = lazy_loader.get_entity_model()
        entity_model = _EntityModel.objects.get(uuid__exact=self.ledger.entity_id)
        fy_key = entity_model.get_fy_for_date(dt=get_localdate())

        try:
            LOOKUP = {
                'entity_model_id__exact': self.ledger.entity_id,
                'entity_unit_id__exact': None,
                'fiscal_year': fy_key,
                'key__exact': _EntityStateModel.KEY_FUND_TRANSFER
            }
            if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
                LOOKUP['fund_id__exact'] = None

            state_model_qs = _EntityStateModel.objects.filter(**LOOKUP).select_related(
                'entity_model').select_for_update()
            state_model = state_model_qs.get()
            state_model.sequence = F('sequence') + 1
            state_model.save(update_fields=['sequence'])
            state_model.refresh_from_db()
            return state_model
        except ObjectDoesNotExist:
            _EntityModel: EntityModel = lazy_loader.get_entity_model()
            entity_model = _EntityModel.objects.get(uuid__exact=self.ledger.entity_id)
            fy_key = entity_model.get_fy_for_date(dt=get_localdate())

            LOOKUP = {
                'entity_model_id': entity_model.uuid,
                'entity_unit_id': None,
                'fiscal_year': fy_key,
                'key': _EntityStateModel.KEY_FUND_TRANSFER,
                'sequence': 1
            }
            if DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES:
                LOOKUP['fund_id'] = None
            state_model = _EntityStateModel.objects.create(**LOOKUP)
            return state_model
        except IntegrityError as e:
            if raise_exception:
                raise e
            return None

    def generate_fund_transfer_number(self, commit: bool = False) -> str:
        """
        Atomic Transaction. Generates the next FundTransferModel document number available. The operation
        will result in two additional queries if the FundTransferModel & LedgerModel is not cached in
        QuerySet via select_related('ledger').

        Parameters
        __________
        commit: bool
            Commits transaction into FundTransferModel.

        Returns
        _______
        str
            A String, representing the generated FundTransferModel instance Document Number.
        """
        if self.can_generate_fund_transfer_number():
            with transaction.atomic(durable=True):

                state_model = None
                while not state_model:
                    state_model = self._get_next_state_model(raise_exception=False)

                seq = str(state_model.sequence).zfill(DJANGO_LEDGER_DOCUMENT_NUMBER_PADDING)
                self.fund_transfer_number = f'{DJANGO_LEDGER_FUND_TRANSFER_NUMBER_PREFIX}-{state_model.fiscal_year}-{seq}'

                if commit:
                    self.save(update_fields=['fund_transfer_number', 'updated'])

        return self.fund_transfer_number

    def generate_descriptive_title(self) -> str:
        return f'Fund Transfer {self.fund_transfer_number}'

    def get_transaction_queryset(self, annotated: bool = False):
        """
        Fetches the TransactionModelQuerySet associated with the BillModel instance.
        """
        TransactionModel = lazy_loader.get_txs_model()
        transaction_model_qs = TransactionModel.objects.all().for_ledger(ledger_model=self.ledger_id)
        if annotated:
            return transaction_model_qs.with_annotated_details()
        return transaction_model_qs

    def get_tx_type(self,
                    acc_bal_type: dict,
                    adjustment_amount: Decimal):
        """
        Determines the transaction type associated with an increase/decrease of an account balance of the financial
        instrument.

        Parameters
        ----------
        acc_bal_type:
            The balance type of the account to be adjusted.
        adjustment_amount: Decimal
            The adjustment, whether positive or negative.

        Returns
        -------
        str
            The transaction type of the account adjustment.
        """
        acc_bal_type = acc_bal_type[0]
        d_or_i = 'd' if adjustment_amount < 0.00 else 'i'
        return self.TX_TYPE_MAPPING[acc_bal_type + d_or_i]

    def get_migrate_state_desc(self) -> str:
        return f'Fund Transfer {self.fund_transfer_number} adjustment.'

    # noinspection PyUnusedLocal
    def migrate_state(self,
                      entity_slug: str,
                      force_migrate: bool = False,
                      commit: bool = True,
                      void: bool = False,
                      je_timestamp: Optional[Union[str, date, datetime]] = None,
                      raise_exception: bool = True):

        """
        Migrates the Fund Transfer financial instrument into the books. The main objective of the migrate_state
        method is to create/update the JournalEntry and TransactionModels necessary to accurately reflect the
        fund transfer state in the books.

        Parameters
        ----------
        entity_slug: str
            The EntityModel slug.
        force_migrate: bool
            Forces migration of the financial instrument bypassing the can_migrate() check.
        commit: bool
            If True the migration will be committed in the database. Defaults to True.
        void: bool
            If True, the migration will perform a VOID actions of the financial instrument.
        je_timestamp: date
            The JournalEntryModel date to be used for this migration.
        raise_exception: bool
            Raises ValidationError if migration is not allowed. Defaults to True.

        Returns
        -------
        None
        """

        if self.can_migrate() or force_migrate:
            if void:
                self.amount = Decimal(0.00)

            if commit:
                JournalEntryModel = lazy_loader.get_journal_entry_model()
                TransactionModel = lazy_loader.get_txs_model()

                if je_timestamp:
                    je_timestamp = validate_io_timestamp(dt=je_timestamp)
                je_timestamp = get_localtime() if not je_timestamp else je_timestamp

                # determine if this is a new fund transfer to be created or an existing transfer to be updated/voided
                # if new, then create the journal entry before proceeding
                je = self.ledger.journal_entries.first()
                if not je:
                    je = JournalEntryModel(
                        fund_id=self.from_fund_id,
                        receiving_fund_id=self.to_fund_id,
                        timestamp=je_timestamp,
                        description=self.get_migrate_state_desc(),
                        origin='create',
                        ledger_id=self.ledger_id
                    )
                    je.save()
                else:
                    je.fund_id = self.from_fund_id
                    je.receiving_fund_id = self.to_fund_id
                    je.origin = 'update'
                    je.save(update_fields=['fund_id', 'receiving_fund_id', 'origin'])

                txs_qs = je.get_transaction_queryset()
                if not txs_qs:
                    txs_list = [
                        TransactionModel(
                            journal_entry=je,
                            amount=abs(self.amount),
                            tx_type=tx_type,
                            account_id=acc_id,
                            description=self.get_migrate_state_desc()
                        ) for tx_type, acc_id in [('credit', self.from_account_id), ('debit', self.to_account_id)]
                    ]
                    TransactionModel.objects.bulk_create(txs_list)
                else:   # update the existing transaction records
                    txs_list = list(txs_qs)
                    for tx in txs_list:
                        tx.amount = abs(self.amount)
                        tx.account_id = self.from_account_id if tx.tx_type == 'credit' else self.to_account_id
                    TransactionModel.objects.bulk_update(txs_list, fields=['amount', 'account_id'])

                je.clean(verify=True)
                if je.is_verified():
                    # usually the journal entry is unlocked and unposted.  But if force_migrate == True,
                    # such as from mark_as_void(), then we have to check if we can still lock and post
                    if not je.is_locked():
                        je.mark_as_locked(commit=False, raise_exception=True)
                    if not je.is_posted():
                        je.mark_as_posted(commit=False, verify=False, raise_exception=True)
                    je.save(update_fields=['posted', 'locked', 'activity'])
        else:
            if raise_exception:
                raise ValidationError(f'{self.REL_NAME_PREFIX.upper()} state migration not allowed')

    def void_state(self, commit: bool = False) -> Dict:
        """
        Determines the VOID state of the financial instrument.

        Parameters
        ----------
        commit: bool
            Commits the new financial instrument state into the model.

        Returns
        -------
        dict
            A dictionary with new amount as key.
        """
        void_state = {
            'amount': Decimal.from_float(0.00),
        }
        if commit:
            self.update_state(void_state)
        return void_state

    def update_state(self, state: Optional[Dict] = None):
        """
        Updates the state on the financial instrument.

        Parameters
        ----------
        state: dict
            Optional user provided state to use.
        """
        if not state:
            state = self.get_state()
        self.amount: Decimal = abs(state['amount'])

    def get_state(self, commit: bool = False):
        """
        Determines the new state of the financial instrument based on progress.

        Parameters
        ----------
        commit: bool
            Commits the new financial instrument state into the model.

        Returns
        -------
        dict
            A dictionary with new amount as key. Value is Decimal type.
        """
        new_state = {
            'amount': self.amount,
        }
        if commit:
            self.update_state(new_state)
        return new_state

    # LOCK/UNLOCK Ledger...
    def lock_ledger(self, commit: bool = False, raise_exception: bool = True):
        """
        Convenience method to lock the LedgerModel associated with thea Fund Transfer.

        Parameters
        ----------
        commit: bool
            Commits the transaction in the database. Defaults to False.
        raise_exception: bool
            If True, raises ValidationError if LedgerModel already locked.
        """
        ledger_model = self.ledger
        if ledger_model.locked:
            if raise_exception:
                raise ValidationError(f'Fund Transfer ledger {ledger_model.name} is already locked...')
            return
        ledger_model.lock(commit, raise_exception=raise_exception)

    def unlock_ledger(self, commit: bool = False, raise_exception: bool = True):
        """
        Convenience method to un-lock the LedgerModel associated with the Fund Transfer.

        Parameters
        ----------
        commit: bool
            Commits the transaction in the database. Defaults to False.
        raise_exception: bool
            If True, raises ValidationError if LedgerModel already unlocked.
        """
        ledger_model = self.ledger
        if not ledger_model.is_locked():
            if raise_exception:
                raise ValidationError(f'Fund Transfer ledger {ledger_model.name} is already unlocked...')
            return
        ledger_model.unlock(commit, raise_exception=raise_exception)

    # POST/UNPOST Ledger...
    def post_ledger(self, commit: bool = False, raise_exception: bool = True):
        """
        Convenience method to post the LedgerModel associated with the Fund Transfer.

        Parameters
        ----------
        commit: bool
            Commits the transaction in the database. Defaults to False.
        raise_exception: bool
            If True, raises ValidationError if LedgerModel already posted.
        """
        ledger_model = self.ledger
        if ledger_model.posted:
            if raise_exception:
                raise ValidationError(f'Fund Transfer ledger {ledger_model.name} is already posted...')
            return
        ledger_model.post(commit, raise_exception=raise_exception)

    def unpost_ledger(self, commit: bool = False, raise_exception: bool = True):
        """
        Convenience method to un-lock the LedgerModel associated with the Fund Transfer.

        Parameters
        ----------
        commit: bool
            Commits the transaction in the database. Defaults to False.
        raise_exception: bool
            If True, raises ValidationError if LedgerModel already unposted.
        """
        ledger_model = self.ledger
        if not ledger_model.is_posted():
            if raise_exception:
                raise ValidationError(f'Fund Transfer ledger {ledger_model.name} is not posted...')
            return
        ledger_model.post(commit, raise_exception=raise_exception)

    # VOID Actions...
    def mark_as_void(self,
                     entity_slug: Optional[str] = None,
                     date_void: Optional[date] = None,
                     commit: bool = False,
                     **kwargs):
        """
        Marks FundTransferModel as Void.

        Parameters
        __________

        entity_slug: str
            Entity slug associated with the FundTransferModel. Avoids additional DB query if passed.

        date_void: date
            FundTransferModel void date. Defaults to localdate() if None.

        commit: bool
            Commits transaction into DB. Defaults to False.
        """
        if not self.can_void():
            raise FundTransferModelValidationError(
                f'Fund Transfer {self.fund_transfer_number} cannot be voided. Must be approved.')

        if date_void:
            if isinstance(date_void, datetime):
                self.date_void = date_void.date()
            elif isinstance(date_void, date):
                self.date_void = date_void
        else:
            self.date_void = get_localdate()

        self.fund_status = self.FUND_TRANSFER_STATUS_VOID
        self.void_state(commit=True)
        self.clean()

        if commit:
            if not entity_slug:
                entity_slug = self.ledger.entity.slug

            self.unlock_ledger(commit=False, raise_exception=False)
            self.migrate_state(
                entity_slug=entity_slug,
                void=True,
                raise_exception=False,
                force_migrate=True)
            self.save()
            self.lock_ledger(commit=False, raise_exception=False)
        fund_transfer_status_void.send_robust(sender=self.__class__,
                                              instance=self,
                                              commited=commit, **kwargs)

    def get_mark_as_void_html_id(self) -> str:
        """
        FundTransferModel Mark as Void HTML ID Tag.

        Returns
        _______
        str
            HTML ID as a String.
        """
        return f'djl-fund-transfer-model-{self.uuid}-mark-as-void'

    def get_mark_as_void_url(self, entity_slug: Optional[str] = None) -> str:
        """
        FundTransferModel Mark-as-Void action URL.

        Parameters
        __________
        entity_slug: str
            Entity Slug kwarg. If not provided, will result in addition DB query if select_related('ledger__entity')
            is not cached on QuerySet.

        Returns
        _______
            FundTransferModel mark-as-void action URL.
        """
        if not entity_slug:
            entity_slug = self.ledger.entity.slug
        return reverse('django_ledger:fund-transfer-action-mark-as-void',
                       kwargs={
                           'entity_slug': entity_slug,
                           'fund_transfer_pk': self.uuid
                       })

    def get_mark_as_void_message(self) -> str:
        """
        Internationalized confirmation message with Fund Transfer Number.

        Returns
        _______
        str
            Mark-as-Void FundTransferModel confirmation message as a String.
        """
        return _('Do you want to void Fund Transfer %s?') % self.fund_transfer_number

    # DELETE ACTIONS...
    def delete(self, force_db_delete: bool = False, using=None, keep_parents=False):
        if not force_db_delete:
            # self.mark_as_canceled(commit=True)
            return None
        if not self.can_delete():
            raise FundTransferModelValidationError(
                message=_(f'Fund Transfer {self.fund_transfer_number} cannot be deleted...')
            )
        return super().delete(using=using, keep_parents=keep_parents)

    # --> URLs <---
    def get_absolute_url(self):
        return reverse('django_ledger:fund-transfer-detail',
                       kwargs={
                           'entity_slug': self.ledger.entity.slug,
                           'fund_transfer_pk': self.uuid
                       })

    def clean(self, commit: bool = True):
        """
        Clean method for FundTransferModel. Results in a DB query if bill number has not been generated and the
        FundTransferModel is eligible to generate a fund_transfer_number.

        Parameters
        __________

        commit: bool
            If True, commits into DB the generated FundTransferModel number if generated.
        """

        super().clean()
        # TODO JJH add clean steps


class FundTransferModel(FundTransferModelAbstract):
    class Meta(FundTransferModelAbstract.Meta):
        abstract = False


# noinspection PyUnusedLocal
def fundtransfermodel_presave(instance: FundTransferModel, **kwargs):
    if instance.can_generate_fund_transfer_number():
        instance.generate_fund_transfer_number(commit=False)


pre_save.connect(receiver=fundtransfermodel_presave, sender=FundTransferModel)
