"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

A Fund is a user-defined accounting category assigned to TransactionModels,
helping to segregate nonprofit operations by distinct funds. Examples of
funds are General Operations, School, Building.

Funds extend double-entry accounting rules and apply to all transactions associated
with them. Non-profits must have every transaction associated with a Fund.  A
Journal Entry will typically have entries crediting and debiting from the same Fund.
However, entries can transfer funds from one Fund to another.

By creating Funds just like Entity Units, we retain certain benefits:
    1. Funds can generate their own financial statements, providing deeper
       insights into the specific operations of the nonprofit by a specific fund.
    2. Funds can be assigned to specific items on Bills and Invoices, offering
       flexibility to track inventory, expenses, or income associated with distinct
       funds.
"""

from random import choices
from string import ascii_lowercase, digits, ascii_uppercase
from typing import Optional, Self
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node, MP_NodeManager, MP_NodeQuerySet

from django_ledger.io.io_core import IOMixIn
from django_ledger.models import lazy_loader
from django_ledger.models.mixins import CreateUpdateMixIn, SlugNameMixIn

FUND_RANDOM_SLUG_SUFFIX = ascii_lowercase + digits


class FundModelValidationError(ValidationError):
    pass


class FundModelQuerySet(MP_NodeQuerySet):
    """
    A custom defined FundModel Queryset.
    """
    def active(self):
        """
        Filters the queryset to include only active items.

        Returns
        -------
        AccountModelQuerySet
            A filtered queryset containing only the items marked as active.
        """
        return self.filter(active=True)


class FundModelManager(MP_NodeManager):

    def get_queryset(self):
        qs = FundModelQuerySet(self.model, using=self._db)
        return qs.annotate(
            _entity_slug=F('entity__slug'),
            _entity_name=F('entity__name'),
        )

    def for_user(self, user_model):
        qs = self.get_queryset()
        if user_model.is_superuser:
            return qs
        return qs.filter(
            Q(entity__admin=user_model) |
            Q(entity__managers__in=[user_model])
        )

    def for_entity(self, entity_slug: str, user_model):
        """
        Fetches a QuerySet of FundModels associated with a specific EntityModel & UserModel.
        May pass an instance of EntityModel or a String representing the EntityModel slug.

        Parameters
        ----------
        entity_slug: str or EntityModel
            The entity slug or EntityModel used for filtering the QuerySet.
        user_model
            Logged in and authenticated django UserModel instance.

        Returns
        -------
        FundModelQuerySet
            Returns a FundModelQuerySet with applied filters.
        """
        qs = self.for_user(user_model)
        if isinstance(entity_slug, lazy_loader.get_entity_model()):
            return qs.filter(
                Q(entity=entity_slug)

            )
        return qs.filter(
            Q(entity__slug__exact=entity_slug)
        )


class FundModelAbstract(MP_Node,
                              IOMixIn,
                              SlugNameMixIn,
                              CreateUpdateMixIn):
    """
    Base implementation of the FundModel.

    Attributes
    ----------
    uuid : UUID
        This is a unique primary key generated for the table. The default value of this field is uuid4().

    slug: str
        A unique, indexed identifier for the FundModel instance used in URLs and queries.

    entity: EntityModel
        The EntityModel associated with this FundModel.

    document_prefix: str
        A predefined prefix automatically incorporated into JournalEntryModel document numbers. Max Length 3.
        May be user defined. Must be unique for the EntityModel.

    active: bool
        Active Funds may transact. Inactive funds are considered archived. Defaults to True.

    hidden: bool
        Hidden Funds will not show on drop down menus on the UI. Defaults to False.
    """
    uuid = models.UUIDField(default=uuid4, editable=False, primary_key=True)
    slug = models.SlugField(max_length=50)
    entity = models.ForeignKey('django_ledger.EntityModel',
                               editable=False,
                               on_delete=models.CASCADE,
                               verbose_name=_('Fund'))
    document_prefix = models.CharField(max_length=3)
    active = models.BooleanField(default=True, verbose_name=_('Is Active'))
    hidden = models.BooleanField(default=False, verbose_name=_('Is Hidden'))

    objects = FundModelManager.from_queryset(queryset_class=FundModelQuerySet)()
    node_order_by = ['uuid']

    class Meta:
        abstract = True
        ordering = ['-created']
        verbose_name = _('Fund Model')
        unique_together = [
            ('entity', 'slug'),
            ('entity', 'document_prefix'),
        ]
        indexes = [
            models.Index(fields=['active']),
            models.Index(fields=['hidden']),
            models.Index(fields=['entity']),
        ]

    def __str__(self):
        return f'{self.entity_name}: {self.name}'

    @property
    def entity_slug(self):
        try:
            return getattr(self, '_entity_slug')
        except AttributeError:
            pass
        return self.entity.slug

    @property
    def entity_name(self):
        try:
            return getattr(self, '_entity_name')
        except AttributeError:
            pass
        return self.entity.name

    def clean(self):
        self.create_fund_slug()

        if not self.document_prefix:
            self.document_prefix = ''.join(choices(ascii_uppercase, k=3))

    def get_dashboard_url(self) -> str:
        """
        The dashboard URL of the FundModel.

        Returns
        -------
        str
            The FundModel instance dashboard URL.
        """
        return reverse('django_ledger:fund-dashboard',
                       kwargs={
                           'entity_slug': self.slug
                       })

    def get_entity_name(self) -> str:
        return self.entity.name

    def create_fund_slug(self,
                                name: Optional[str] = None,
                                force: bool = False,
                                add_suffix: bool = True,
                                k: int = 5) -> str:
        """
        Automatically generates a FundModel slug. If slug is present, will not be replaced.
        Called during the clean() method.

        Parameters
        ----------
        force: bool
            Forces generation of new slug if already present.
        name: str
            The name used to create slug. If none, the fund name will be used.
        add_suffix: bool
            Adds a random suffix to the slug. Defaults to True.
        k: int
            Length of the suffix if add_suffix is True. Defaults to 5.

        Returns
        -------
        str
            The FundModel slug, regardless if generated or not.
        """
        if not self.slug or force:
            if not name:
                name = f'{self.name} Fund'
            fund_slug = slugify(name)
            if add_suffix:
                suffix = ''.join(choices(FUND_RANDOM_SLUG_SUFFIX, k=k))
                fund_slug = f'{fund_slug}-{suffix}'
            self.slug = fund_slug
        return self.slug

    def get_absolute_url(self):
        return reverse(
            viewname='django_ledger:fund-detail',
            kwargs={
                'entity_slug': self.entity.slug,
                'fund_slug': self.slug
            }
        )


class FundModel(FundModelAbstract):
    """
    Base Model Class for FundModel
    """

    class Meta(FundModelAbstract.Meta):
        abstract = False

    @classmethod
    def create_default_funds(cls, entity, activate: bool = False) -> list[Self]:
        DEFAULT_FUNDS = [
            ('General Operations', 'GO'),
            ('School', 'SC'),
            ('Building', 'BL'),
        ]

        fund_list = []
        for name, prefix in DEFAULT_FUNDS:
            fund = FundModel(
                name=name,
                document_prefix=prefix,
                entity=entity,
                active=activate,
            )
            fund.create_fund_slug(name=name)
            FundModel.add_root(instance=fund)
            fund_list.append(fund)

        return fund_list