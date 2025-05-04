"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

This module serves as a core component of the Django Ledger framework, providing an optimized interface and
utilities for handling financial transactions, journal entries, and generating financial statements.
It is designed to allow efficient interaction with the database, minimizing Python's memory usage by emphasizing
database-level aggregations while enforcing proper accounting principles.

Key Features:
-------------
1. **Transaction and Journal Management**:
   - Provides capabilities for creating, validating, and balancing transactions at the database level.
   - Supports integration of Closing Entries as optimizations for financial data aggregation.

2. **Validation Utilities**:
   - Validates transaction balances, timestamps, and input data for minimal errors.
   - Ensures consistency with Django Ledger configurations, such as handling timezone-awareness and closing dates.

3. **Database Interaction**:
   - Aggregation and querying of financial data at the database layer to improve memory efficiency.
   - Implements advanced filtering options for transactions based on attributes like activity, account roles, business units, and time periods.
   - Leverages Closing Entries as "checkpoints" to minimize aggregation workload on large datasets.

4. **Financial Statement Reports**:
    - Offers functionalities to generate financial statements, including:
     - Balance Sheet
     - Income Statement
     - Cash Flow Statement
    - Supports PDF generation for these reports (if PDF support is enabled).

5. **Extensibility**:
   - Implements a layered architecture with reusable mixins (`IODatabaseMixIn`, `IOReportMixIn`, `IOMixIn`) that allow developers to customize behavior for specific use cases or extend functionality when needed.

6. **Middleware and Ratios**:
   - Includes middleware support for handling roles, financial groups, and ratios as additional processing layers for generated reports.

Classes:
--------
- `IOResult`:
  A data carrier class for managing aggregated transaction and account balance data during digest operations.

- `IODatabaseMixIn`:
  Handles database interactions for aggregating transaction data efficiently and applying accounting rules.

- `IOReportMixIn`:
  Offers methods for generating financial reports, including support for PDF output (if enabled).

- `IOMixIn`:
  Combines database operations and reporting features into a single reusable mixin for comprehensive I/O management.

Functions:
----------
- **Utility Functions**:
    - `diff_tx_data()`: Validates whether the credits and debits for a given transaction dataset are balanced.
    - `check_tx_balance()`: Ensures transaction datasets are corrected to be balanced if requested.
    - `validate_io_timestamp()`: Ensures that input dates or timestamps are valid and timezone-aware.
    - `get_localtime()`, `get_localdate()`: Retrieve local time or local date based on Django's timezone settings.
    - `validate_dates()`: Validates and parses `from_date` and `to_date` inputs.

- **Digest Operations**:
    - `database_digest()`: Processes and aggregates transactions directly in the database with support for filters such as activity, role, and period.
    - `python_digest()`: Applies additional processing and group-by operations on transaction data after database-level aggregation.
    - `digest()`: A unified entry point for performing database digests and Python-level post-processing, with options to process roles, groups, ratios, and financial statements.

- **Report Data Generation**:
    - `get_balance_sheet_statement()`, `get_income_statement()`, `get_cash_flow_statement()`: Generate specific financial statements, with optional PDF output.
    - `get_financial_statements()`: Generate all key financial statements together (Balance Sheet, Income Statement, Cash Flow Statement).

Error Handling:
---------------
- **Custom Exceptions**:
  - `IOValidationError`: Raised for input validation errors during transaction or journal entry processing.

Supported Features:
-------------------
- Database-level transaction aggregation for performance optimization.
- Timezone-aware operations for timestamp handling.
- Modular architecture leveraging mixins for different components.
- Middleware for advanced role processing and financial grouping.
- Optional PDF generation using settings from Django Ledger.

Notes:
------
- Ensure `DJANGO_LEDGER_PDF_SUPPORT_ENABLED` is properly configured to enable PDF output in financial reports.
- Closing Entries play a critical role in improving aggregation times for entities with significant transactions.
- The module is designed to work seamlessly with Django's ORM and custom models through utilities provided in
  the Django Ledger framework.
"""
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from itertools import groupby
from pathlib import Path
from typing import List, Set, Union, Tuple, Optional, Dict

from django.conf import settings as global_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.models import Sum, QuerySet, F, DecimalField, When, Case
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from django_ledger import settings
from django_ledger.io import roles as roles_module, CREDIT, DEBIT
from django_ledger.io.io_context import IODigestContextManager
from django_ledger.io.io_middleware import (
    AccountRoleIOMiddleware,
    AccountGroupIOMiddleware,
    JEActivityIOMiddleware,
    BalanceSheetIOMiddleware,
    IncomeStatementIOMiddleware,
    CashFlowStatementIOMiddleware
)
from django_ledger.io.ratios import FinancialRatioManager
from django_ledger.io.utils import validate_io_timestamp, validate_activity, check_tx_balance
from django_ledger.models.journal_entry import JournalEntryModelAbstract
from django_ledger.models.transactions import TransactionModelAbstract
from django_ledger.models.utils import lazy_loader
from django_ledger.settings import DJANGO_LEDGER_PDF_SUPPORT_ENABLED

UserModel = get_user_model()


def validate_dates(
        from_date: Optional[Union[str, datetime, date]] = None,
        to_date: Optional[Union[str, datetime, date]] = None
) -> Tuple[date, date]:
    """
    Validates and converts the input dates to date objects. This function ensures that the
    provided `from_date` and `to_date` are correctly parsed into `date` objects. If the dates
    are given as strings or datetime objects, they will be validated and converted to `date`
    objects accordingly.

    Parameters
    ----------
    from_date : str, datetime, date, optional
        The start date, which can be provided as a string, datetime, or date object.
        If not provided, it may default depending on the implementation of the
        `validate_io_timestamp` function.
    to_date : str, datetime, date, optional
        The end date, which can be provided as a string, datetime, or date object.
        If not provided, it may default depending on the implementation of the
        `validate_io_timestamp` function.

    Returns
    -------
    Tuple[date, date]
        A tuple containing the validated `from_date` and `to_date` as `date` objects.
        The first element is the validated start date, and the second element is the
        validated end date.
    """
    from_date = validate_io_timestamp(from_date, no_parse_localdate=False)
    to_date = validate_io_timestamp(to_date)
    return from_date, to_date


class IOValidationError(ValidationError):
    pass


@dataclass
class IOResult:
    """
    Represents the input-output result schema for data aggregation and processing.

    This class encapsulates details related to database aggregation, closing entry
    lookup parameters, and the final dataset used for evaluation. It also provides
    utility to check bounded date constraints for closing entry lookups.

    Attributes
    ----------
    db_from_date : Optional[date]
        The starting date for database aggregation queries.
    db_to_date : Optional[date]
        The ending date for database aggregation queries.
    ce_match : bool
        Indicates whether closing entry matches are applicable.
    ce_from_date : Optional[date]
        The starting date for closing entry lookups.
    ce_to_date : Optional[date]
        The ending date for closing entry lookups.
    txs_queryset
        The final queryset used for evaluation, typically containing processed
        transaction data.
    accounts_digest : Optional[List[Dict]]
        A summary or aggregation of account balances derived from the processed
        data.
    """
    # DB Aggregation...
    db_from_date: Optional[date] = None
    db_to_date: Optional[date] = None

    # Closing Entry lookup...
    ce_match: bool = False
    ce_from_date: Optional[date] = None
    ce_to_date: Optional[date] = None

    # the final queryset to evaluate...
    txs_queryset = None

    # the aggregated account balance...
    accounts_digest: Optional[List[Dict]] = None

    @property
    def is_bounded(self) -> bool:
        return all([
            self.ce_from_date is not None,
            self.ce_to_date is not None,
        ])


class IODatabaseMixIn:
    """
    Mix-in class for database interactions and aggregation for IO models.

    This class is designed to encapsulate several common behaviors for models
    related to database queries and aggregations in the context of IO operations
    such as transactions, ledger models, and entity models. It facilitates the
    derivation of specific models, validation of query parameters, and execution
    of data aggregation queries with flexible filtering and grouping options.

    Attributes
    ----------
    TRANSACTION_MODEL_CLASS : NoneType or Type
        Specifies the Django model class for transactions. If None, a lazy loader
        will be used to determine the model dynamically.
    JOURNAL_ENTRY_MODEL_CLASS : NoneType or Type
        Specifies the Django model class for journal entries. If None, a lazy
        loader will be used to determine the model dynamically.
    """

    TRANSACTION_MODEL_CLASS = None
    JOURNAL_ENTRY_MODEL_CLASS = None

    def is_entity_model(self):
        """
        Check if the instance is an EntityModel.

        Returns
        -------
        bool
            True if the instance is an entity model, False otherwise.
        """
        return isinstance(self, lazy_loader.get_entity_model())

    def is_ledger_model(self):
        """
        Checks if the current instance is a LedgerModel.

        Returns
        -------
        bool
            True if the instance is of type ledger model, False otherwise.
        """
        return isinstance(self, lazy_loader.get_ledger_model())

    def is_entity_unit_model(self):
        """
        Checks if the current instance is an EntityUnitModel.

        Returns
        -------
        bool
            `True` if the object is an instance of the entity unit model;
            `False` otherwise.
        """
        return isinstance(self, lazy_loader.get_entity_unit_model())

    def get_entity_model_from_io(self):
        """
        Retrieves the entity model associated with the current instance.

        This method determines the type of the current model instance and retrieves
        the corresponding entity model if applicable. If the instance itself is an
        EntityModel, it returns itself. If the instance is a ledgerModel or EntityUnitModel
        model, the associated entity model is retrieved from its attributes.

        Returns
        -------
        entity : EntityModel
            Retrieves the associated entity model if the instance is a ledger
            or entity unit model.
        """
        if self.is_entity_model():
            return self
        elif self.is_ledger_model():
            return getattr(self, 'entity')
        elif self.is_entity_unit_model():
            return getattr(self, 'entity')
        raise IOValidationError(
            message=_(f'IODatabaseMixIn not compatible with {self.__class__.__name__} model.')
        )

    def get_transaction_model(self) -> type[TransactionModelAbstract]:
        """
        Retrieve the transaction model class used for handling transactions.

        The method checks whether a specific transaction model class is explicitly
        set via the `TRANSACTION_MODEL_CLASS` attribute. If set, it returns that
        class as the transaction model. If not set, it falls back to a default
        transaction model obtained from the `lazy_loader.get_txs_model()` method.

        Returns
        -------
        type
            The transaction model class defined in `TRANSACTION_MODEL_CLASS` or
            the default transaction model provided by `lazy_loader.get_txs_model()`.
        """
        if self.TRANSACTION_MODEL_CLASS is not None:
            return self.TRANSACTION_MODEL_CLASS
        return lazy_loader.get_txs_model()

    def get_journal_entry_model(self) -> type[JournalEntryModelAbstract]:
        """
        Retrieves the class model for journal entries. If the `JOURNAL_ENTRY_MODEL_CLASS`
        attribute is set, it returns its value. Otherwise, it dynamically loads and
        returns the journal entry model using the `lazy_loader`.

        Returns
        -------
        Type
            The journal entry model class, either explicitly defined in
            `JOURNAL_ENTRY_MODEL_CLASS` or loaded dynamically.
        """
        if self.JOURNAL_ENTRY_MODEL_CLASS is not None:
            return self.JOURNAL_ENTRY_MODEL_CLASS
        return lazy_loader.get_journal_entry_model()

    def database_digest(self,
                        entity_slug: Optional[str] = None,
                        unit_slug: Optional[str] = None,
                        user_model: Optional[UserModel] = None,
                        from_date: Optional[Union[date, datetime]] = None,
                        to_date: Optional[Union[date, datetime]] = None,
                        by_activity: bool = False,
                        by_tx_type: bool = False,
                        by_period: bool = False,
                        by_unit: bool = False,
                        activity: Optional[str] = None,
                        role: str = Optional[str],
                        accounts: Optional[Union[str, List[str], Set[str]]] = None,
                        posted: bool = True,
                        exclude_zero_bal: bool = True,
                        use_closing_entries: Optional[bool] = False,
                        **kwargs) -> IOResult:
        """
        Aggregates transaction data based on the provided parameters to generate a
        digest of financial entries. This method is designed to work with various
        models (EntityModel, EntityUnitModel, LedgerModel) and processes
        transactions, including handling closing entries to optimize database
        queries. The resulting data can be customized based on specific filters
        or aggregation criteria, such as activity, transaction type, or time periods.

        Parameters
        ----------
        entity_slug : Optional[str]
            The identifier for the entity. Used to filter transactions for a specific
            entity in cases where the model operates at the entity level.
        unit_slug : Optional[str]
            The identifier for the unit. Valid when filtering transactions for a
            specific unit within an entity.
        user_model : Optional[UserModel]
            The user model instance. Represents the user context in which the
            transaction filtering applies.
        from_date : Optional[Union[date, datetime]]
            The starting date for filtering transactions. Aggregates data from
            the given date if specified.
        to_date : Optional[Union[date, datetime]]
            The ending date for filtering transactions. Aggregates data up to this
            date if specified.
        by_activity : bool
            Determines whether results should be aggregated by activity. Defaults
            to False.
        by_tx_type : bool
            Indicates if results should be grouped by transaction type. Defaults
            to False.
        by_period : bool
            Determines if results should be grouped by time period (e.g., months).
            Defaults to False.
        by_unit : bool
            Indicates whether transactions should be grouped by entity unit.
            Defaults to False.
        activity : Optional[str]
            A specific activity identifier to filter results. If provided, only
            transactions related to this activity will be included.
        role : Optional[str]
            A specific role to filter transactions by. Transactions matching this
            role will be included in the aggregation.
        accounts : Optional[Union[str, List[str], Set[str]]]
            Specifies accounts to filter by. Can be a single account or a list/set
            of accounts. Filters transactions associated with the provided accounts.
        posted : bool
            Indicates whether to filter transactions that are posted (committed).
            Defaults to True.
        exclude_zero_bal : bool
            If True, transactions with zero-balance amounts will be excluded.
            Defaults to True.
        use_closing_entries : Optional[bool]
            Specifies whether closing entries should be used to optimize database
            aggregation. If not provided (i.e. equals None), the value is determined
            by the system-global setting.
        kwargs : dict
            Additional parameters that can be passed for extended flexibility or
            customization when filtering and processing transactions.

        Returns
        -------
        IOResult
            An object containing the aggregated results, filtered transaction querysets,
            and metadata such as database query bounds or details about closing
            entry matches.
        """

        TransactionModel = self.get_transaction_model()

        # get_initial txs_queryset... where the IO model is operating from??...
        if self.is_entity_model():
            if entity_slug:
                # noinspection PyUnresolvedReferences
                if entity_slug != self.slug:
                    # noinspection PyUnresolvedReferences
                    raise IOValidationError('Inconsistent entity_slug. '
                                            f'Provided {entity_slug} does not match actual {self.slug}')
            if unit_slug:

                # noinspection PyUnresolvedReferences
                txs_queryset_init = TransactionModel.objects.for_entity(
                    user_model=user_model,
                    entity_slug=entity_slug or self.slug
                ).for_unit(unit_slug=unit_slug)

            else:
                txs_queryset_init = TransactionModel.objects.for_entity(
                    user_model=user_model,
                    entity_slug=self
                )
        elif self.is_entity_unit_model():
            if not entity_slug:
                raise IOValidationError(
                    'Calling digest from Entity Unit requires entity_slug explicitly for safety')

            txs_queryset_init = TransactionModel.objects.for_entity(
                user_model=user_model,
                entity_slug=entity_slug,
            ).for_unit(unit_slug=unit_slug or self)

        elif self.is_ledger_model():
            if not entity_slug:
                raise IOValidationError(
                    'Calling digest from Ledger Model requires entity_slug explicitly for safety')

            txs_queryset_init = TransactionModel.objects.for_entity(
                entity_slug=entity_slug,
                user_model=user_model,
            ).for_ledger(ledger_model=self)

        else:
            raise IOValidationError(
                message=f'Cannot call digest from {self.__class__.__name__}'
            )

        io_result = IOResult(db_to_date=to_date, db_from_date=from_date)
        txs_queryset_agg = txs_queryset_init.not_closing_entry()
        txs_queryset_from_closing_entry = txs_queryset_init.none()
        txs_queryset_to_closing_entry = txs_queryset_init.none()

        USE_CLOSING_ENTRIES = settings.DJANGO_LEDGER_USE_CLOSING_ENTRIES
        if use_closing_entries is not None:
            USE_CLOSING_ENTRIES = use_closing_entries

        # use closing entries to minimize DB aggregation if possible and activated...
        if USE_CLOSING_ENTRIES:
            txs_queryset_closing_entry = txs_queryset_init.is_closing_entry()
            entity_model = self.get_entity_model_from_io()

            # looking up available dates...
            ce_from_date = entity_model.get_closing_entry_for_date(io_date=from_date, inclusive=False)
            ce_to_date = entity_model.get_closing_entry_for_date(io_date=to_date)

            # unbounded lookup, no date match
            # finding the closest closing entry to aggregate from if present...
            if not from_date and not ce_to_date:
                ce_alt_from_date = entity_model.get_nearest_next_closing_entry(io_date=to_date)

                # if there's a suitable closing entry...
                if ce_alt_from_date:
                    txs_queryset_from_closing_entry = txs_queryset_closing_entry.filter(
                        journal_entry__timestamp__date=ce_alt_from_date)
                    io_result.ce_match = True
                    io_result.ce_from_date = ce_alt_from_date

                    # limit db aggregation to unclosed entries...
                    io_result.db_from_date = ce_alt_from_date + timedelta(days=1)
                    io_result.db_to_date = to_date

                    # print(f'Unbounded lookup no date match. Closest from_dt: {ce_alt_from_date}...')

            # unbounded lookup, exact to_date match...
            elif not from_date and ce_to_date:
                txs_queryset_to_closing_entry = txs_queryset_closing_entry.filter(
                    journal_entry__timestamp__date=ce_to_date)
                io_result.ce_match = True
                io_result.ce_to_date = ce_to_date

                # no need to DB aggregate, just use closing entry...
                io_result.db_from_date = None
                io_result.db_to_date = None
                txs_queryset_agg = TransactionModel.objects.none()

            # bounded exact from_date and to_date match...
            elif ce_from_date and ce_to_date:
                txs_queryset_from_closing_entry = txs_queryset_closing_entry.filter(
                    journal_entry__timestamp__date=ce_from_date)

                txs_queryset_to_closing_entry = txs_queryset_closing_entry.filter(
                    journal_entry__timestamp__date=ce_to_date)

                io_result.ce_match = True
                io_result.ce_from_date = ce_from_date
                io_result.ce_to_date = ce_to_date

                # no need to aggregate, use both closing entries...
                io_result.db_from_date = None
                io_result.db_to_date = None
                txs_queryset_agg = TransactionModel.objects.none()

        txs_queryset_closing_entry = txs_queryset_from_closing_entry | txs_queryset_to_closing_entry

        if io_result.db_from_date:
            txs_queryset_agg = txs_queryset_agg.from_date(from_date=io_result.db_from_date)

        if io_result.db_to_date:
            txs_queryset_agg = txs_queryset_agg.to_date(to_date=io_result.db_to_date)

        txs_queryset = txs_queryset_agg | txs_queryset_closing_entry

        if exclude_zero_bal:
            txs_queryset = txs_queryset.filter(amount__gt=0.00)

        if posted:
            txs_queryset = txs_queryset.posted()

        if accounts:
            if isinstance(accounts, str):
                accounts = [accounts]
            txs_queryset = txs_queryset.for_accounts(account_list=accounts)

        if activity:
            if isinstance(activity, str):
                activity = [activity]
            txs_queryset = txs_queryset.for_activity(activity_list=activity)

        if role:
            txs_queryset = txs_queryset.for_roles(role_list=role)

        # Cleared transaction filter via KWARGS....
        cleared_filter = kwargs.get('cleared')
        if cleared_filter is not None:
            if cleared_filter in [True, False]:
                txs_queryset = txs_queryset.is_cleared() if cleared_filter else txs_queryset.not_cleared()
            else:
                raise IOValidationError(
                    message=f'Invalid value for cleared filter: {cleared_filter}. '
                            f'Valid values are True, False'
                )

        # Reconciled transaction filter via KWARGS....
        reconciled_filter = kwargs.get('reconciled')
        if reconciled_filter is not None:
            if reconciled_filter in [True, False]:
                txs_queryset = txs_queryset.is_reconciled() if reconciled_filter else txs_queryset.not_reconciled()
            else:
                raise IOValidationError(
                    message=f'Invalid value for reconciled filter: {reconciled_filter}. '
                            f'Valid values are True, False'
                )

        if io_result.is_bounded:
            # noinspection PyUnboundLocalVariable
            txs_queryset = txs_queryset.annotate(
                amount_io=Case(
                    When(
                        journal_entry__timestamp__date=ce_from_date,
                        then=-F('amount')),
                    default=F('amount'),
                    output_field=DecimalField()
                ))

        VALUES = [
            'account__uuid',
            'account__balance_type',
            'account__code',
            'account__name',
            'account__role',
            'account__coa_model__slug',
            'tx_type',
        ]

        ANNOTATE: Dict = {'balance': Sum('amount')}
        if io_result.is_bounded:
            ANNOTATE = {'balance': Sum('amount_io')}

        ORDER_BY = ['account__uuid']

        if by_unit:
            ORDER_BY.append('journal_entry__entity_unit__uuid')
            VALUES += ['journal_entry__entity_unit__uuid', 'journal_entry__entity_unit__name']

        if by_period:
            ORDER_BY.append('journal_entry__timestamp')
            ANNOTATE['dt_idx'] = TruncMonth('journal_entry__timestamp')

        if by_activity:
            ORDER_BY.append('journal_entry__activity')
            VALUES.append('journal_entry__activity')

        if by_tx_type:
            ORDER_BY.append('tx_type')
            VALUES.append('tx_type')

        io_result.txs_queryset = txs_queryset.values(*VALUES).annotate(**ANNOTATE).order_by(*ORDER_BY)
        return io_result

    def python_digest(self,
                      user_model: Optional[UserModel] = None,
                      entity_slug: Optional[str] = None,
                      unit_slug: Optional[str] = None,
                      to_date: Optional[Union[date, datetime, str]] = None,
                      from_date: Optional[Union[date, datetime, str]] = None,
                      equity_only: bool = False,
                      activity: str = None,
                      role: Optional[Union[Set[str], List[str]]] = None,
                      accounts: Optional[Union[Set[str], List[str]]] = None,
                      signs: bool = True,
                      by_unit: bool = False,
                      by_activity: bool = False,
                      by_tx_type: bool = False,
                      by_period: bool = False,
                      use_closing_entries: Optional[bool] = False,
                      force_queryset_sorting: bool = False,
                      **kwargs) -> IOResult:
        """
        Computes and returns the digest of transactions for a given entity, unit,
        and optional filters such as date range, account role, and activity. The
        digest includes aggregated balances by specified group-by keys.

        Parameters
        ----------
        user_model : Optional[UserModel]
            The user model to be used for the computation. Defaults to None.
        entity_slug : Optional[str]
            The slug representing the entity to compute the digest for. Defaults
            to None.
        unit_slug : Optional[str]
            The slug representing the unit within the entity. Defaults to None.
        to_date : Optional[Union[date, datetime, str]]
            The end date for the transaction filter. Defaults to None.
        from_date : Optional[Union[date, datetime, str]]
            The start date for the transaction filter. Defaults to None.
        equity_only : bool
            Whether to compute results only for earnings-related accounts. Defaults
            to False.
        activity : str
            An optional activity filter for transactions. Defaults to None.
        role : Optional[Union[Set[str], List[str]]]
            The account roles to include in the digest. Defaults to None.
        accounts : Optional[Union[Set[str], List[str]]]
            A list or set of specific accounts to include. Defaults to None.
        signs : bool
            Whether to adjust the signs for the account balances based on balance type and account role.
            Defaults to True.
        by_unit : bool
            Whether to group the results by unit. Defaults to False.
        by_activity : bool
            Whether to group the results by activity. Defaults to False.
        by_tx_type : bool
            Whether to group the results by transaction type. Defaults to False.
        by_period : bool
            Whether to group the results by period (year and month). Defaults to False.
        use_closing_entries : Optional[bool]
            Whether to include closing entries in the computation. Defaults to False.
        force_queryset_sorting : bool
            Whether to force sorting of the transaction queryset. Defaults to  False.
        **kwargs : dict
            Additional keyword arguments passed to the computation.

        Returns
        -------
        IOResult
            An object containing the transaction queryset, grouped and aggregated
            account balances, and other relevant digest information.
        """

        if equity_only:
            role = roles_module.GROUP_EARNINGS

        io_result = self.database_digest(
            user_model=user_model,
            entity_slug=entity_slug,
            unit_slug=unit_slug,
            to_date=to_date,
            from_date=from_date,
            by_unit=by_unit,
            by_activity=by_activity,
            by_tx_type=by_tx_type,
            by_period=by_period,
            activity=activity,
            role=role,
            accounts=accounts,
            use_closing_entries=use_closing_entries,
            **kwargs)

        for tx_model in io_result.txs_queryset:
            if tx_model['account__balance_type'] != tx_model['tx_type']:
                tx_model['balance'] = -tx_model['balance']

        gb_key = lambda a: (
            a['account__uuid'],
            a.get('journal_entry__entity_unit__uuid') if by_unit else None,
            a.get('dt_idx').year if by_period else None,
            a.get('dt_idx').month if by_period else None,
            a.get('journal_entry__activity') if by_activity else None,
            a.get('tx_type') if by_tx_type else None,
        )

        if force_queryset_sorting:
            io_result.txs_queryset = list(io_result.txs_queryset)
            io_result.txs_queryset.sort(key=gb_key)

        accounts_gb_code = groupby(io_result.txs_queryset, key=gb_key)
        accounts_digest = [self.aggregate_balances(k, g) for k, g in accounts_gb_code]

        for acc in accounts_digest:
            acc['balance_abs'] = abs(acc['balance'])

        if signs:
            for acc in accounts_digest:
                if any([
                    all([acc['role_bs'] == roles_module.BS_ASSET_ROLE,
                         acc['balance_type'] == CREDIT]),
                    all([acc['role_bs'] in (
                            roles_module.BS_LIABILITIES_ROLE,
                            roles_module.BS_EQUITY_ROLE
                    ),
                         acc['balance_type'] == DEBIT])
                ]):
                    acc['balance'] = -acc['balance']

        io_result.accounts_digest = accounts_digest
        return io_result

    @staticmethod
    def aggregate_balances(k, g):
        """
        Aggregates balances from grouped data, providing a summarized representation of
        account attributes and their balances over a specified period. The function is
        used to compile essential details such as account identifiers, roles, activity,
        and balance, summarizing them for further processing or presentation.

        Parameters
        ----------
        k : tuple
            A tuple consisting of grouped key values. Expected structure:
            - The first element represents the account UUID.
            - The second element represents the unit UUID.
            - The third and fourth elements represent the period year and month, respectively.
            - The sixth element represents the transaction type.

        g : iterable
            An iterable of grouped account data, typically containing dictionaries with
            detailed account properties and their respective balance information.

        Returns
        -------
        dict
            A dictionary containing the aggregated balance information and related
            attributes, structured with the following keys:
            - 'account_uuid'
            - 'coa_slug'
            - 'unit_uuid'
            - 'unit_name'
            - 'activity'
            - 'period_year'
            - 'period_month'
            - 'role_bs'
            - 'role'
            - 'code'
            - 'name'
            - 'balance_type'
            - 'tx_type'
            - 'balance'
        """
        gl = list(g)
        return {
            'account_uuid': k[0],
            'coa_slug': gl[0]['account__coa_model__slug'],
            'unit_uuid': k[1],
            'unit_name': gl[0].get('journal_entry__entity_unit__name'),
            'activity': gl[0].get('journal_entry__activity'),
            'period_year': k[2],
            'period_month': k[3],
            'role_bs': roles_module.BS_ROLES.get(gl[0]['account__role']),
            'role': gl[0]['account__role'],
            'code': gl[0]['account__code'],
            'name': gl[0]['account__name'],
            'balance_type': gl[0]['account__balance_type'],
            'tx_type': k[5],
            'balance': sum(a['balance'] for a in gl),
        }

    def digest(self,
               entity_slug: Optional[str] = None,
               unit_slug: Optional[str] = None,
               to_date: Optional[Union[date, datetime, str]] = None,
               from_date: Optional[Union[date, datetime, str]] = None,
               user_model: Optional[UserModel] = None,
               accounts: Optional[Union[Set[str], List[str]]] = None,
               role: Optional[Union[Set[str], List[str]]] = None,
               activity: Optional[str] = None,
               signs: bool = True,
               process_roles: bool = False,
               process_groups: bool = False,
               process_ratios: bool = False,
               process_activity: bool = False,
               equity_only: bool = False,
               by_period: bool = False,
               by_unit: bool = False,
               by_activity: bool = False,
               by_tx_type: bool = False,
               balance_sheet_statement: bool = False,
               income_statement: bool = False,
               cash_flow_statement: bool = False,
               use_closing_entries: Optional[bool] = None,
               **kwargs) -> IODigestContextManager:
        """
        Processes financial data and generates various financial statements, ratios, or activity digests
        based on the provided arguments. The method applies specific processing pipelines, such as role
        processing, grouping, ratio computation, activity-based operations, or generating financial
        statements like balance sheet, income statement, and cash flow statement.

        Parameters
        ----------
        entity_slug : Optional[str]
            The slug identifier for the entity to process the financial data for.
        unit_slug : Optional[str]
            The slug identifier for the specific unit of the entity to filter the data for.
        to_date : Optional[Union[date, datetime, str]]
            The upper limit of the date range for which the data will be processed. Can be a `date`,
            `datetime`, or ISO 8601 formatted `str`.
        from_date : Optional[Union[date, datetime, str]]
            The lower limit of the date range for which the data will be processed. Can be a `date`,
            `datetime`, or ISO 8601 formatted `str`.
        user_model : Optional[UserModel]
            A user model instance to filter data or apply user-specific permissions during processing.
        accounts : Optional[Union[Set[str], List[str]]]
            A collection of account identifiers to filter the financial data to process.
        role : Optional[Union[Set[str], List[str]]]
            A collection of roles used to filter or organize the data during processing.
        activity : Optional[str]
            Specific activity identifier to filter or process the data for.
        signs : bool, default=True
            If `True`, account roles with predefined signs will be applied to the financial data.
        process_roles : bool, default=False
            If `True`, processes account roles and organizes financial data accordingly.
        process_groups : bool, default=False
            If `True`, processes and organizes the financial data into predetermined account groups.
        process_ratios : bool, default=False
            If `True`, computes and processes financial ratios for the provided data.
        process_activity : bool, default=False
            If `True`, specific activity-based computation or segregation will be executed.
        equity_only : bool, default=False
            Processes only equity-specific accounts if set to `True`.
        by_period : bool, default=False
            Organizes or groups the output by accounting periods if `True`.
        by_unit : bool, default=False
            Organizes or processes data specific to each unit when set to `True`.
        by_activity : bool, default=False
            Groups or segregates the processed data by activity when `True`.
        by_tx_type : bool, default=False
            Groups or organizes the result by transaction type when `True`.
        balance_sheet_statement : bool, default=False
            If `True`, prepares a balance sheet statement as part of the processing.
        income_statement : bool, default=False
            If `True`, generates an income statement as part of the processed result.
        cash_flow_statement : bool, default=False
            If `True`, prepares a cash flow statement based on the provided data.
        use_closing_entries : Optional[bool]
            Specifies whether to account for closing entries in the financial statement computation.
            Default is None, i.e. use system default.
        **kwargs
            Additional named arguments that can be passed to adjust the behavior of specific processing
            modules or middleware.

        Returns
        -------
        IODigestContextManager
            A context manager instance containing the processed financial data and results, including
            financial statements, ratios, or any activity digest generated as per the input parameters.
        """
        if balance_sheet_statement:
            from_date = None

        if cash_flow_statement:
            by_activity = True

        if activity:
            activity = validate_activity(activity)
        if role:
            role = roles_module.validate_roles(role)

        from_date, to_date = validate_dates(from_date, to_date)

        io_state = dict()
        io_state['io_model'] = self
        io_state['from_date'] = from_date
        io_state['to_date'] = to_date
        io_state['by_unit'] = by_unit
        io_state['unit_slug'] = unit_slug
        io_state['entity_slug'] = entity_slug
        io_state['by_period'] = by_period
        io_state['by_activity'] = by_activity
        io_state['by_tx_type'] = by_tx_type

        io_result: IOResult = self.python_digest(
            user_model=user_model,
            accounts=accounts,
            role=role,
            activity=activity,
            entity_slug=entity_slug,
            unit_slug=unit_slug,
            to_date=to_date,
            from_date=from_date,
            signs=signs,
            equity_only=equity_only,
            by_period=by_period,
            by_unit=by_unit,
            by_activity=by_activity,
            by_tx_type=by_tx_type,
            use_closing_entries=use_closing_entries,
            **kwargs
        )

        io_state['io_result'] = io_result
        io_state['accounts'] = io_result.accounts_digest

        # IO Middleware...

        if process_roles:
            roles_mgr = AccountRoleIOMiddleware(
                io_data=io_state,
                by_period=by_period,
                by_unit=by_unit
            )

            io_state = roles_mgr.digest()

        if any([
            process_groups,
            balance_sheet_statement,
            income_statement,
            cash_flow_statement
        ]):
            group_mgr = AccountGroupIOMiddleware(
                io_data=io_state,
                by_period=by_period,
                by_unit=by_unit
            )
            io_state = group_mgr.digest()

            # todo: migrate this to group manager...
            io_state['group_account']['GROUP_ASSETS'].sort(
                key=lambda acc: roles_module.ROLES_ORDER_ASSETS.index(acc['role']))
            io_state['group_account']['GROUP_LIABILITIES'].sort(
                key=lambda acc: roles_module.ROLES_ORDER_LIABILITIES.index(acc['role']))
            io_state['group_account']['GROUP_CAPITAL'].sort(
                key=lambda acc: roles_module.ROLES_ORDER_CAPITAL.index(acc['role']))

        if process_ratios:
            ratio_gen = FinancialRatioManager(io_data=io_state)
            io_state = ratio_gen.digest()

        if process_activity:
            activity_manager = JEActivityIOMiddleware(io_data=io_state, by_unit=by_unit, by_period=by_period)
            activity_manager.digest()

        if balance_sheet_statement:
            balance_sheet_mgr = BalanceSheetIOMiddleware(io_data=io_state)
            io_state = balance_sheet_mgr.digest()

        if income_statement:
            income_statement_mgr = IncomeStatementIOMiddleware(io_data=io_state)
            io_state = income_statement_mgr.digest()

        if cash_flow_statement:
            cfs = CashFlowStatementIOMiddleware(io_data=io_state)
            io_state = cfs.digest()

        return IODigestContextManager(io_state=io_state)

    # noinspection PyUnusedLocal
    def commit_txs(self,
                   je_timestamp: Union[str, datetime, date],
                   je_txs: List[Dict],
                   je_posted: bool = False,
                   je_ledger_model=None,
                   je_unit_model=None,
                   je_desc=None,
                   je_origin=None,
                   force_je_retrieval: bool = False,
                   **kwargs):
        """
        Commits a set of financial transactions to a journal entry, after performing
        validation checks. Validations include ensuring balanced transactions, ensuring
        timestamp integrity, and verifying relationships between models. This method
        creates or retrieves a journal entry based on the provided details and assigns
        the given transactions accordingly, supporting conditional posting.

        Parameters
        ----------
        je_timestamp : str or datetime or date
            The timestamp for the journal entry. Validates against entity's closed
            periods and is required to be in a valid format.
        je_txs : list of dict
            A list of transactions to be committed, each represented as a dictionary.
            Each transaction should include keys such as 'account', 'amount', 'tx_type',
            and 'description'.
        je_posted : bool, optional
            Whether the created or retrieved journal entry should be marked as posted
            after verification. Defaults to False.
        je_ledger_model : object, optional
            An optional instance of LedgerModel used for validating ledger associations.
            If not provided, defaults to the current ledger model.
        je_unit_model : object, optional
            An optional instance of EntityUnitModel used for validating entity unit
            associations with transactions.
        je_desc : str, optional
            A description for the journal entry. Defaults to None if not provided.
        je_origin : str, optional
            Specifies the origin or source of the journal entry. Defaults to None.
        force_je_retrieval : bool, optional
            Whether to force retrieval of an existing journal entry with the given
            timestamp instead of creating a new one. Defaults to False.
        **kwargs : dict
            Additional keyword arguments that may be required for handling specific
            customization details during journal entry creation or retrieval.

        Returns
        -------
        tuple
            A tuple containing the journal entry model (je_model) and a list of
            transaction models (txs_models) created or associated with the journal entry.

        Raises
        ------
        IOValidationError
            Raised for various validation errors including invalid timestamps, attempting
            to commit on locked or closed ledgers, association errors with ledger or
            entity models, and inability to retrieve a required journal entry.
        """
        TransactionModel = self.get_transaction_model()
        JournalEntryModel = self.get_journal_entry_model()

        # Validates that credits/debits balance.
        check_tx_balance(je_txs, perform_correction=False)
        je_timestamp = validate_io_timestamp(dt=je_timestamp)

        entity_model = self.get_entity_model_from_io()

        if entity_model.last_closing_date:
            if isinstance(je_timestamp, datetime):
                if entity_model.last_closing_date >= je_timestamp.date():
                    raise IOValidationError(
                        message=_(
                            f'Cannot commit transactions. The journal entry date {je_timestamp} is on a closed period.')
                    )
            elif isinstance(je_timestamp, date):
                if entity_model.last_closing_date >= je_timestamp:
                    raise IOValidationError(
                        message=_(
                            f'Cannot commit transactions. The journal entry date {je_timestamp} is on a closed period.')
                    )

        if self.is_ledger_model():
            # noinspection PyUnresolvedReferences
            if self.is_locked():
                raise IOValidationError(
                    message=_('Cannot commit on locked ledger')
                )

        # if calling from EntityModel must pass an instance of LedgerModel...
        if all([
            isinstance(self, lazy_loader.get_entity_model()),
            je_ledger_model is None
        ]):
            raise IOValidationError('Committing from EntityModel requires an instance of LedgerModel')

        # Validates that the provided LedgerModel id valid...
        if all([
            isinstance(self, lazy_loader.get_entity_model()),
            je_ledger_model is not None,
        ]):
            # noinspection PyUnresolvedReferences
            if je_ledger_model.entity_id != self.uuid:
                raise IOValidationError(f'LedgerModel {je_ledger_model} does not belong to {self}')

        # Validates that the provided EntityUnitModel id valid...
        if all([
            isinstance(self, lazy_loader.get_entity_model()),
            je_unit_model is not None,
        ]):
            # noinspection PyUnresolvedReferences
            if je_unit_model.entity_id != self.uuid:
                raise IOValidationError(f'EntityUnitModel {je_unit_model} does not belong to {self}')

        if not je_ledger_model:
            je_ledger_model = self

        if force_je_retrieval:
            try:
                if isinstance(je_timestamp, (datetime, str)):
                    # noinspection PyUnusedLocal
                    je_model = je_ledger_model.journal_entries.get(timestamp__exact=je_timestamp)
                elif isinstance(je_timestamp, date):
                    # noinspection PyUnusedLocal
                    je_model = je_ledger_model.journal_entries.get(timestamp__date__exact=je_timestamp)
                else:
                    raise IOValidationError(message=_(f'Invalid timestamp type {type(je_timestamp)}'))
            except ObjectDoesNotExist:
                raise IOValidationError(
                    message=_(f'Unable to retrieve Journal Entry model with Timestamp {je_timestamp}')
                )
        else:
            je_model = JournalEntryModel(
                ledger=je_ledger_model,
                entity_unit=je_unit_model,
                description=je_desc,
                timestamp=je_timestamp,
                origin=je_origin,
                posted=False,
                locked=False
            )
            je_model.save(verify=False)

        # todo: add method to process list of transaction models...
        txs_models = [
            (
                TransactionModel(
                    account=txm_kwargs['account'],
                    amount=txm_kwargs['amount'],
                    tx_type=txm_kwargs['tx_type'],
                    description=txm_kwargs['description'],
                    journal_entry=je_model,
                ), txm_kwargs) for txm_kwargs in je_txs
        ]

        for tx, txm_kwargs in txs_models:
            staged_tx_model = txm_kwargs.get('staged_tx_model')
            if staged_tx_model:
                staged_tx_model.transaction_model = tx

        txs_models = TransactionModel.objects.bulk_create(i[0] for i in txs_models)
        je_model.save(verify=True, post_on_verify=je_posted)
        return je_model, txs_models


class IOReportMixIn:
    """
    Provides functionality for generating and managing financial reports.

    This mixin class facilitates the generation, processing, and management of
    various financial statements, including balance sheet statements, income
    statements, and cash flow statements. Reports can be created in multiple
    formats, such as plain data representation or as PDF files. The class
    integrates support for financial data digestion and report serialization,
    including saving PDF reports to specified file paths. Common use cases include
    generating summarized financial data for reporting purposes and outputting
    them in PDF format.

    Attributes
    ----------
    PDF_REPORT_ORIENTATION : str
        Indicates the orientation of the generated PDF reports ('P' for portrait, 'L' for landscape).
    PDF_REPORT_MEASURE_UNIT : str
        Specifies the measurement unit used in the PDF reports (e.g., 'mm', 'cm').
    PDF_REPORT_PAGE_SIZE : str
        Defines the size of the pages in the generated PDF reports (e.g., 'Letter', 'A4').
    ReportTuple : namedtuple
        A tuple structure containing three fields: `balance_sheet_statement`,
        `income_statement`, and `cash_flow_statement`. Each field represents a
        respective financial report.
    """
    PDF_REPORT_ORIENTATION = 'P'
    PDF_REPORT_MEASURE_UNIT = 'mm'
    PDF_REPORT_PAGE_SIZE = 'Letter'

    ReportTuple = namedtuple('ReportTuple',
                             field_names=[
                                 'balance_sheet_statement',
                                 'income_statement',
                                 'cash_flow_statement'
                             ])

    def digest_balance_sheet(self,
                             to_date: Union[date, datetime],
                             user_model: Optional[UserModel] = None,
                             txs_queryset: Optional[QuerySet] = None,
                             **kwargs: Dict) -> IODigestContextManager:
        """
        Digest the balance sheet for a specific time period, user, and optionally a specific set
        of transactions. Returns a context manager for digesting the specified balance sheet data.

        Parameters
        ----------
        to_date : Union[date, datetime]
            The date till which the balance sheet needs to be digested, including transactions
            occurring on this date.

        user_model : Optional[UserModel], optional
            The model instance representing the user whose balance sheet is to be
            digested. This can be `None` to indicate no specific user.

        txs_queryset : Optional[QuerySet], optional
            A queryset containing specific transactions to be included in the calculation.
            If not provided, all transactions up to `to_date` will be considered.

        kwargs : Dict
            Additional keyword arguments that can be used for the digestion process.
            Allows flexible filtering or additional specifications.

        Returns
        -------
        IODigestContextManager
            A context manager for handling the digestion process of the balance sheet.
        """
        # self.digest() is in IODatabaseMixin
        # noinspection PyUnresolvedReferences
        return self.digest(
            user_model=user_model,
            to_date=to_date,
            balance_sheet_statement=True,
            txs_queryset=txs_queryset,
            as_io_digest=True,
            signs=True,
            **kwargs
        )

    def get_balance_sheet_statement(self,
                                    to_date: Union[date, datetime],
                                    subtitle: Optional[str] = None,
                                    filepath: Optional[Path] = None,
                                    filename: Optional[str] = None,
                                    user_model: Optional[UserModel] = None,
                                    save_pdf: bool = False,
                                    **kwargs
                                    ) -> IODigestContextManager:
        """
        Generates a balance sheet statement with an option to save it as a PDF file.

        This method fetches and processes financial data to create a balance sheet
        statement using the provided date range, user model, and additional optional
        settings. It supports generating a PDF output for the balance sheet if
        configured. The class responsible for PDF generation is dynamically loaded,
        allowing modularity and flexibility.

        Note that PDF generation functionality is dependent on the presence of the
        `DJANGO_LEDGER_PDF_SUPPORT_ENABLED` flag. If the flag is not enabled, the
        method raises an exception.

        Parameters
        ----------
        to_date : Union[date, datetime]
            The end date for the balance sheet report. The data will be considered
            up to this date for the financial statement.
        subtitle : Optional[str], default=None
            An optional subtitle for the generated report. This can be used to include
            additional context or descriptions in the report.
        filepath : Optional[Path], default=None
            Specifies the directory path where the PDF file should be saved. If not
            provided, a default directory is used based on application settings.
        filename : Optional[str], default=None
            Name of the file to save the PDF report. Defaults to an automatically
            generated filename if not provided.
        user_model : Optional[UserModel], default=None
            The user context associated with the balance sheet report. Includes
            permissions or specific user-related data.
        save_pdf : bool, default=False
            A flag indicating whether the balance sheet should be saved as a PDF. If
            True, the method generates and stores the PDF in the specified location.
        **kwargs
            Additional keyword arguments required for generating the balance sheet.
            It may include filtering, formatting, or any other relevant parameters.

        Returns
        -------
        IODigestContextManager
            The context manager object handling the generated balance sheet, either in
            memory or in saved PDF format. If the `save_pdf` option is enabled, the PDF
            report is saved at the specified location.
        """
        if not DJANGO_LEDGER_PDF_SUPPORT_ENABLED:
            raise IOValidationError(
                message=_('PDF support not enabled. Install PDF support from Pipfile.')
            )

        io_digest = self.digest_balance_sheet(
            to_date=to_date,
            user_model=user_model,
            **kwargs
        )

        BalanceSheetReport = lazy_loader.get_balance_sheet_report_class()
        report = BalanceSheetReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest,
            report_subtitle=subtitle
        )
        if save_pdf:
            base_dir = Path(global_settings.BASE_DIR) if not filepath else Path(filepath)
            filename = report.get_pdf_filename() if not filename else filename
            filepath = base_dir.joinpath(filename)
            report.create_pdf_report()
            report.output(filepath)
        return report

    def digest_income_statement(self,
                                from_date: Union[date, datetime],
                                to_date: Union[date, datetime],
                                user_model: Optional[UserModel] = None,
                                txs_queryset: Optional[QuerySet] = None,
                                **kwargs) -> IODigestContextManager:
        """
        Digest the income statement within the specified date range and optionally filter
        by user and transaction queryset.

        This method generates a digest context manager for the income statement,
        allowing granular control over the data derived within the requested range
        and applying any additional filters provided. It supports optional user and
        transaction queryset filters for tailored data processing.

        Parameters
        ----------
        from_date : Union[date, datetime]
            The starting date for filtering the income statement.
        to_date : Union[date, datetime]
            The ending date for filtering the income statement.
        user_model : Optional[UserModel], optional
            An optional user model instance to filter income statement data
            by a specific user.
        txs_queryset : Optional[QuerySet], optional
            An optional transaction queryset to filter the income statement
            by specific transaction records.
        **kwargs : dict
            Additional keyword arguments for customization or requirements in
            the income statement digest generation process.

        Returns
        -------
        IODigestContextManager
            A context manager containing the processed income statement data.
        """
        # noinspection PyUnresolvedReferences
        return self.digest(
            user_model=user_model,
            from_date=from_date,
            to_date=to_date,
            income_statement=True,
            txs_queryset=txs_queryset,
            as_io_digest=True,
            sings=True,
            **kwargs
        )

    def get_income_statement(self,
                             from_date: Union[date, datetime],
                             to_date: Union[date, datetime],
                             subtitle: Optional[str] = None,
                             filepath: Optional[Path] = None,
                             filename: Optional[str] = None,
                             user_model: Optional[UserModel] = None,
                             txs_queryset: Optional[QuerySet] = None,
                             save_pdf: bool = False,
                             **kwargs
                             ):
        """
        Generates an income statement report for a specific time period and allows optional PDF
        saving functionality. The function utilizes configurations, user-provided parameters,
        and transactions data to create an income statement report, which can either be returned
        as a report object or saved as a PDF on the filesystem.

        Parameters
        ----------
        from_date : date or datetime
            The starting date of the income statement period. Must be provided.
        to_date : date or datetime
            The ending date of the income statement period. Must be provided.
        subtitle : str, optional
            An optional subtitle for the income statement report.
        filepath : Path, optional
            The directory path where the PDF report should be saved, if `save_pdf` is set to True.
        filename : str, optional
            The filename for the PDF report. If not provided, a default filename is generated.
        user_model : UserModel, optional
            A user model instance, providing additional context or filtering for the income
            statement generation.
        txs_queryset : QuerySet, optional
            A queryset containing transactions data to be included in the income statement
            report. If not provided, transactions may be automatically determined by other
            parameters or configurations.
        save_pdf : bool
            Indicates whether the generated income statement should be saved as a PDF file.
            Defaults to False.
        **kwargs :
            Additional optional keyword arguments for further customization or filtering.

        Raises
        ------
        IOValidationError
            Raised if PDF support is not enabled in the configuration. The error provides a
            message suggesting installing PDF support.

        Returns
        -------
        IncomeStatementReport
            A configured instance of the IncomeStatementReport class, representing the
            generated income statement report. If `save_pdf` is True, the report will also
            be saved as a PDF file at the specified location.
        """
        if not DJANGO_LEDGER_PDF_SUPPORT_ENABLED:
            raise IOValidationError(
                message=_('PDF support not enabled. Install PDF support from Pipfile.')
            )

        io_digest = self.digest_income_statement(
            from_date=from_date,
            to_date=to_date,
            user_model=user_model,
            txs_queryset=txs_queryset,
            **kwargs
        )
        IncomeStatementReport = lazy_loader.get_income_statement_report_class()
        report = IncomeStatementReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest,
            report_subtitle=subtitle
        )
        if save_pdf:
            base_dir = Path(global_settings.BASE_DIR) if not filepath else Path(filepath)
            filename = report.get_pdf_filename() if not filename else filename
            filepath = base_dir.joinpath(filename)
            report.create_pdf_report()
            report.output(filepath)
        return report

    def digest_cash_flow_statement(self,
                                   from_date: Union[date, datetime],
                                   to_date: Union[date, datetime],
                                   user_model: Optional[UserModel] = None,
                                   txs_queryset: Optional[QuerySet] = None,
                                   **kwargs) -> IODigestContextManager:
        """
        Generates a digest of the cash flow statement for a specified date range, user model,
        and optional transaction query set. This method utilizes an internal digest
        mechanism to compile and return the cash flow statement context.

        Parameters
        ----------
        from_date : Union[date, datetime]
            The start date of the period for the cash flow statement.
        to_date : Union[date, datetime]
            The end date of the period for the cash flow statement.
        user_model : Optional[UserModel]
            The user model instance for which the digest is generated. If None, the
            default user model is used.
        txs_queryset : Optional[QuerySet]
            An optional queryset of transactions to include in the digest. If None,
            defaults to all transactions within the date range.
        **kwargs : dict
            Additional keyword arguments passed to the digest function.

        Returns
        -------
        IODigestContextManager
            Context manager providing the digested cash flow statement.
        """
        # noinspection PyUnresolvedReferences
        return self.digest(
            user_model=user_model,
            from_date=from_date,
            to_date=to_date,
            cash_flow_statement=True,
            txs_queryset=txs_queryset,
            as_io_digest=True,
            signs=True,
            **kwargs
        )

    def get_cash_flow_statement(self,
                                from_date: Union[date, datetime],
                                to_date: Union[date, datetime],
                                subtitle: Optional[str] = None,
                                filepath: Optional[Path] = None,
                                filename: Optional[str] = None,
                                user_model: Optional[UserModel] = None,
                                save_pdf: bool = False,
                                **kwargs):
        """
        Generates a cash flow statement report within a specified date range and provides
        an option to save the report as a PDF file. The method retrieves financial data, processes
        it into a structured cash flow statement, and uses a PDF report generator to create the report.

        Parameters
        ----------
        from_date : Union[date, datetime]
            The start date for the cash flow statement.
        to_date : Union[date, datetime]
            The end date for the cash flow statement.
        subtitle : Optional[str], default=None
            Subtitle text for the report.
        filepath : Optional[Path], default=None
            The directory path where the PDF report will be saved. Defaults to the
            base directory if not provided.
        filename : Optional[str], default=None
            The name of the PDF report file. If not provided, a default name is generated.
        user_model : Optional[UserModel], default=None
            The user model instance, optionally used for filtering or customization of the
            report content.
        save_pdf : bool, default=False
            Flag to save the generated report as a PDF file.
        kwargs : dict
            Additional keyword arguments that are passed to the `digest_cash_flow_statement`
            method for further customization or additional processing.

        Returns
        -------
        CashFlowStatementReport
            An instance of the cash flow statement report class, either saved as a PDF if
            `save_pdf` is True or ready for further processing or display.

        Raises
        ------
        IOValidationError
            If PDF support is not enabled in the system's Django ledger configuration.
        """
        if not DJANGO_LEDGER_PDF_SUPPORT_ENABLED:
            raise IOValidationError(
                message=_('PDF support not enabled. Install PDF support from Pipfile.')
            )

        io_digest = self.digest_cash_flow_statement(
            from_date=from_date,
            to_date=to_date,
            user_model=user_model,
            **kwargs
        )

        CashFlowStatementReport = lazy_loader.get_cash_flow_statement_report_class()
        report = CashFlowStatementReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest,
            report_subtitle=subtitle
        )
        if save_pdf:
            base_dir = Path(global_settings.BASE_DIR) if not filepath else Path(filepath)
            filename = report.get_pdf_filename() if not filename else filename
            filepath = base_dir.joinpath(filename)
            report.create_pdf_report()
            report.output(filepath)
        return report

    def digest_financial_statements(self,
                                    from_date: Union[date, datetime],
                                    to_date: Union[date, datetime],
                                    user_model: Optional[UserModel] = None,
                                    **kwargs) -> IODigestContextManager:
        """
        Digest financial statements within a given date range, allowing optional
        customization through `kwargs`. The method processes and provides access
        to balance sheet statements, income statements, and cash flow statements
        for the specified date range. Results are encapsulated in an
        IODigestContextManager for ease of management.

        The function provides flexibility to include a user model for domain-specific
        processing needs while ensuring support for both date and datetime objects.

        Parameters
        ----------
        from_date : date or datetime
            The starting date of the range for which financial statements are
            to be processed.

        to_date : date or datetime
            The ending date of the range for which financial statements are
            to be processed.

        user_model : Optional[UserModel], default=None
            A user model instance that allows for context-specific processing
            during the digestion of financial statements.

        kwargs : dict
            Additional optional parameters that may be used to further
            customize the processing of financial statements.

        Returns
        -------
        IODigestContextManager
            Represents the context manager containing the digested financial
            statements for the specified date range.
        """
        # noinspection PyUnresolvedReferences
        return self.digest(
            from_date=from_date,
            to_date=to_date,
            user_model=user_model,
            balance_sheet_statement=True,
            income_statement=True,
            cash_flow_statement=True,
            as_io_digest=True,
            **kwargs
        )

    def get_financial_statements(self,
                                 from_date: Union[date, datetime],
                                 to_date: Union[date, datetime],
                                 dt_strfmt: str = '%Y%m%d',
                                 user_model: Optional[UserModel] = None,
                                 save_pdf: bool = False,
                                 filepath: Optional[Path] = None,
                                 **kwargs) -> ReportTuple:
        """
        Generates financial statements for a specified date range, optionally saving them as
        PDF files. This method consolidates the balance sheet, income statement, and cash flow
        statement for the given dates. If PDF saving is enabled, the financial statements will
        be saved to the specified path or the application's base directory. The results are
        returned as a tuple containing the reports.

        Parameters
        ----------
        from_date : Union[date, datetime]
            The start date for the financial statements.
        to_date : Union[date, datetime]
            The end date for the financial statements.
        dt_strfmt : str
            The string format used for the filenames of the generated PDF reports. Defaults to
            '%Y%m%d'.
        user_model : Optional[UserModel], optional
            The user model instance, if applicable. Defaults to None.
        save_pdf : bool, optional
            Determines whether to save the generated financial statements as PDF files.
            Defaults to False.
        filepath : Optional[Path], optional
            The directory path where the PDF files will be saved. If not provided, the files will
            be saved in the application's base directory. Defaults to None.
        **kwargs
            Additional keyword arguments for customizing financial statement generation.

        Returns
        -------
        ReportTuple
            A named tuple containing the generated balance sheet, income statement, and cash
            flow statement as objects.

        Raises
        ------
        IOValidationError
            Raised if PDF support is not enabled in the application configuration.
        """
        if not DJANGO_LEDGER_PDF_SUPPORT_ENABLED:
            raise IOValidationError(
                message=_('PDF support not enabled. Install PDF support from Pipfile.')
            )

        io_digest = self.digest_financial_statements(
            from_date=from_date,
            to_date=to_date,
            user_model=user_model,
            **kwargs
        )

        BalanceSheetReport = lazy_loader.get_balance_sheet_report_class()
        bs_report = BalanceSheetReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest
        )
        IncomeStatementReport = lazy_loader.get_income_statement_report_class()
        is_report = IncomeStatementReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest
        )
        CashFlowStatementReport = lazy_loader.get_cash_flow_statement_report_class()
        cfs_report = CashFlowStatementReport(
            self.PDF_REPORT_ORIENTATION,
            self.PDF_REPORT_MEASURE_UNIT,
            self.PDF_REPORT_PAGE_SIZE,
            io_digest=io_digest
        )

        if save_pdf:
            base_dir = Path(global_settings.BASE_DIR) if not filepath else Path(filepath)
            bs_report.create_pdf_report()
            bs_report.output(base_dir.joinpath(bs_report.get_pdf_filename(dt_strfmt=dt_strfmt)))

            is_report.create_pdf_report()
            is_report.output(base_dir.joinpath(is_report.get_pdf_filename(from_dt=from_date, dt_strfmt=dt_strfmt)))

            cfs_report.create_pdf_report()
            cfs_report.output(base_dir.joinpath(cfs_report.get_pdf_filename(from_dt=from_date, dt_strfmt=dt_strfmt)))

        return self.ReportTuple(
            balance_sheet_statement=bs_report,
            income_statement=is_report,
            cash_flow_statement=cfs_report
        )


class IOMixIn(
    IODatabaseMixIn,
    IOReportMixIn
):
    """
    Provides input and output functionalities by mixing in database and
    reporting environments.

    This class is a mixin that combines functionalities from IODatabaseMixIn
    and IOReportMixIn. It is designed to integrate database input/output
    operations with report generation features seamlessly.
    """
