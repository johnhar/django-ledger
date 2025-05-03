import graphene

from django_ledger.contrib.django_ledger_graphene.coa.schema import ChartOfAccountsModelType
from django_ledger.contrib.django_ledger_graphene.entity.schema import EntityModelQuery, EntityModelType


class Query(
    EntityModelQuery,
    # ChartOfAccountsModelQuery
    # CustomerQuery,
    # BillListQuery,
    # AccountListQuery,
    # BankAccountQuery        ,
    # ChartOfAccountsQuery,
    # UnitOfMeasureQuery,
    # VendorsQuery,
    # EntityUnitQuery,
    # FundQuery,
    # LedgerQuery,
    # TransactionsQuery,
    # JournalEntryQuery,
    # PurchaseOrderQuery,
    # QueryUser,
):
    pass


# class Mutation(
#     # CustomerMutations,
#     # BankAccountMutations,
#     # AuthMutation,
# ):
#     pass


# noinspection PyTypeChecker
schema = graphene.Schema(
    types=[
        EntityModelType,
        ChartOfAccountsModelType
    ],
    query=Query,
    # mutation=Mutation
)
