"""
These helper functions are shared by Django Ledger IO modules and models.
These are placed here to avoid circular imports.
"""
from datetime import date, datetime
from random import choice
from typing import Union, Optional
from zoneinfo import ZoneInfo

from django.conf import settings as global_settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import is_naive, make_aware, localtime, localdate

from django_ledger import settings
from django_ledger.exceptions import InvalidDateInputError, TransactionNotInBalanceError
from django_ledger.io.roles import DEBIT, CREDIT
from django_ledger.models.utils import lazy_loader


def validate_io_timestamp(
        dt: Union[str, date, datetime],
        no_parse_localdate: bool = True
) -> Optional[Union[datetime, date]]:
    """
    Validates and processes a given date or datetime input and returns a processed
    datetime or date object depending on the parsing and processing results. This
    function is designed to handle multiple types of inputs including strings,
    date objects, and datetime objects, while accounting for timezone awareness
    and other scenarios where inputs may be invalid or improperly formed.

    Parameters
    ----------
    dt : Union[str, date, datetime]
        The input value to be validated and processed. This can be a string
        representing a date or datetime, a `date` object, or a `datetime` object.
        If the input is invalid or cannot be parsed, an error will be raised.
    no_parse_localdate : bool, optional
        A flag to indicate if the local date should be returned directly when the
        input cannot be parsed or is unavailable. Defaults to True.

    Returns
    -------
    Optional[Union[datetime, date]]
        Returns a timezone-aware or naive `datetime` object that was processed
        depending on input and timezone settings. May also return a `date` object
        in specific scenarios. Returns `None` if the input is empty or invalid.

    Raises
    ------
    InvalidDateInputError
        Raised when the provided string cannot be parsed into a valid `date` or
        `datetime` object.

    Notes
    -----
    - The function handles both timezone-aware and naive datetime objects, and
      attempts to make objects timezone-aware when global time zone settings
      are enabled.
    - String inputs are first attempted to be parsed into `date` objects before
      attempting to parse them into `datetime` objects if the initial attempt fails.
    - When `no_parse_localdate` is True, the function defaults to returning the
      local time for cases where parsing is not possible.
    """
    if not dt:
        return None

    if isinstance(dt, datetime):
        if is_naive(dt):
            return make_aware(
                value=dt,
                timezone=ZoneInfo('UTC')
            )
        return dt

    elif isinstance(dt, str):
        # try to parse a date object from string...
        fdt = parse_date(dt)
        if not fdt:
            # try to parse a datetime object from string...
            fdt = parse_datetime(dt)
            if not fdt:
                raise InvalidDateInputError(
                    message=f'Could not parse date from {dt}'
                )
            elif is_naive(fdt):
                fdt = make_aware(fdt)
        if global_settings.USE_TZ:
            return make_aware(
                datetime.combine(
                    fdt, datetime.min.time(),
                ))
        return datetime.combine(fdt, datetime.min.time())

    elif isinstance(dt, date):
        if global_settings.USE_TZ:
            return make_aware(
                value=datetime.combine(dt, datetime.min.time())
            )
        return datetime.combine(dt, datetime.min.time())

    if no_parse_localdate:
        return localtime()
    return None


def get_localtime(tz=None) -> datetime:
    """
    Retrieve the local time based on the specified timezone.

    Determines the local time depending on whether timezone support (``USE_TZ``) is
    enabled in global settings. If timezone support is enabled, it uses the
    `localtime` function to obtain the local time according to the provided
    timezone. If timezone support is disabled, it defaults to the current time
    with respect to the given timezone.

    Parameters
    ----------
    tz : timezone or None, optional
        The timezone to determine the local time. If `None`, defaults to the system
        timezone.

    Returns
    -------
    datetime
        A datetime object representing the calculated local time.
    """
    if global_settings.USE_TZ:
        return localtime(timezone=tz)
    return datetime.now(tz=tz)


def get_localdate() -> date:
    """
        Fetches the current local date, optionally considering time zone settings.

        This function retrieves the current local date. If the global settings indicate
        the use of time zones (`USE_TZ` is True), the date is determined based on the
        local time zone. Otherwise, the date is based on the system's local time without
        any time zone consideration.

        Returns
        -------
        date
            The current local date, adjusted for the time zone setting if applicable.
    """
    if global_settings.USE_TZ:
        return localdate()
    return datetime.today()


def validate_activity(activity: str, raise_404: bool = False):
    """
    Validates the given activity against the list of valid activities and raises
    appropriate exceptions if it is invalid.

    This function checks whether the provided activity is included in the list
    of valid activities defined within the JournalEntryModel. It raises a
    ValidationError or Http404 error depending on the value of `raise_404`
    if the activity is not valid. If the activity is valid or not provided,
    it returns the activity unaltered.

    Parameters
    ----------
    activity : str
        The activity string to validate against the valid activities.
    raise_404 : bool, optional
        Whether to raise an Http404 error instead of ValidationError when the
        activity is invalid. Default is False.

    Returns
    -------
    str
        The activity string if it is valid.

    Raises
    ------
    ValidationError
        If the activity is invalid and `raise_404` is False.
    Http404
        If the activity is invalid and `raise_404` is True.
    """
    # idea: move to model???...
    JournalEntryModel = lazy_loader.get_journal_entry_model()
    valid = activity in JournalEntryModel.VALID_ACTIVITIES
    if activity and not valid:
        exception = ValidationError(f'{activity} is invalid. Choices are {JournalEntryModel.VALID_ACTIVITIES}.')
        if raise_404:
            raise Http404(exception)
        raise exception
    return activity


def check_tx_balance(tx_data: list, perform_correction: bool = False) -> bool:
    """
    Checks the validity of a list of transactions and optionally corrects the balance
    discrepancy if any. The function assesses whether the total balance from the
    transactions satisfies the predefined tolerance settings. If `perform_correction`
    is enabled, it adjusts the transactions iteratively to correct discrepancies.

    Parameters
    ----------
    tx_data : list
        A list of transaction data where each transaction contains information
        such as amount and type ('debit' or 'credit').
    perform_correction : bool, optional
        A flag indicating whether to attempt to correct balance discrepancies
        in the transaction data. Defaults to False.

    Returns
    -------
    bool
        Returns True if the transactions are valid and satisfy the balance
        tolerance (with or without correction). Returns False otherwise.
    """
    if tx_data:

        IS_TX_MODEL, is_valid, diff = diff_tx_data(tx_data, raise_exception=perform_correction)

        if not perform_correction and abs(diff):
            return False

        if not perform_correction and abs(diff) > settings.DJANGO_LEDGER_TRANSACTION_MAX_TOLERANCE:
            return False

        while not is_valid:
            tx_type_choice = choice([DEBIT, CREDIT])
            txs_candidates = list(tx for tx in tx_data if tx['tx_type'] == tx_type_choice)
            if len(txs_candidates) > 0:
                tx = choice(list(tx for tx in tx_data if tx['tx_type'] == tx_type_choice))
                if any([diff > 0 and tx_type_choice == DEBIT,
                        diff < 0 and tx_type_choice == CREDIT]):
                    if IS_TX_MODEL:
                        tx.amount += settings.DJANGO_LEDGER_TRANSACTION_CORRECTION
                    else:
                        tx['amount'] += settings.DJANGO_LEDGER_TRANSACTION_CORRECTION

                elif any([diff < 0 and tx_type_choice == DEBIT,
                          diff > 0 and tx_type_choice == CREDIT]):
                    if IS_TX_MODEL:
                        tx.amount -= settings.DJANGO_LEDGER_TRANSACTION_CORRECTION
                    else:
                        tx['amount'] += settings.DJANGO_LEDGER_TRANSACTION_CORRECTION

                IS_TX_MODEL, is_valid, diff = diff_tx_data(tx_data)

    return True


def diff_tx_data(tx_data: list, raise_exception: bool = True):
    """
    Calculates the difference between credits and debits in a transaction dataset
    and validates if the transactions are in balance. Supports both dictionary-like
    data and `TransactionModel` objects.

    The function checks whether the provided transaction data is in balance by
    comparing the sum of credits and debits. If they are not in balance, the function
    optionally raises an exception when the discrepancy exceeds the defined tolerance
    limit. It also indicates whether the transaction data is modeled using
    `TransactionModel`.

    Parameters
    ----------
    tx_data : list
        A list of transactions, which can either be dictionaries or instances
        of `TransactionModel`. Each transaction must have an `amount` field and
        a `tx_type` field. The `tx_type` should be either 'credit' or 'debit'.
    raise_exception : bool, optional
        Whether to raise an exception if the transactions are not balanced and
        the difference exceeds the defined tolerance value. Defaults to True.

    Returns
    -------
    tuple
        A tuple containing the following:
            1. `IS_TX_MODEL` (bool): Indicates whether the transaction data uses the `TransactionModel`.
            2. `is_valid` (bool): Indicates whether the total credits match the total debits within the defined tolerance.
            3. `diff` (float): The difference between the sum of credits and the sum of debits.

    Raises
    ------
    ValidationError
        If the `tx_data` is neither a list of dictionaries nor a list of
        `TransactionModel` instances.
    TransactionNotInBalanceError
        If the transactions are not in balance (when `is_valid` is False), the
        difference exceeds the maximum tolerance, and `raise_exception` is True.
    """
    IS_TX_MODEL = False
    TransactionModel = lazy_loader.get_txs_model()

    if isinstance(tx_data[0], TransactionModel):
        credits = sum(tx.amount for tx in tx_data if tx.tx_type == CREDIT)
        debits = sum(tx.amount for tx in tx_data if tx.tx_type == DEBIT)
        IS_TX_MODEL = True
    elif isinstance(tx_data[0], dict):
        credits = sum(tx['amount'] for tx in tx_data if tx['tx_type'] == CREDIT)
        debits = sum(tx['amount'] for tx in tx_data if tx['tx_type'] == DEBIT)
    else:
        raise ValidationError('Only Dictionary or TransactionModel allowed.')

    is_valid = (credits == debits)
    diff = credits - debits

    if not is_valid and abs(diff) > settings.DJANGO_LEDGER_TRANSACTION_MAX_TOLERANCE:
        if raise_exception:
            raise TransactionNotInBalanceError(
                f'Invalid tx data. Credits and debits must match. Currently cr: {credits}, db {debits}.'
                f'Max Tolerance {settings.DJANGO_LEDGER_TRANSACTION_MAX_TOLERANCE}'
            )

    return IS_TX_MODEL, is_valid, diff
