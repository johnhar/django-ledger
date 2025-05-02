import graphene
from graphene import relay
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from django_ledger.models import JournalEntryModel, JournalEntryModelQuerySet


class JournalEntryNode(DjangoObjectType):
    class Meta:
        model = JournalEntryModel
        filter_fields = {
            'activity': ['exact', 'icontains', 'istartswith'],
            'timestamp': ['exact'],
            'description': ['exact'],
        }
        interfaces = (relay.Node,)


class JournalEntryQuery(graphene.ObjectType):
    all_journal_entries = DjangoFilterConnectionField(
        JournalEntryNode, slug_name=graphene.String(
            required=True), pk_ledger=graphene.UUID())

    # noinspection PyUnusedLocal
    @staticmethod
    def resolve_all_journal_entry(info, slug_name, pk_ledger, **kwargs) -> JournalEntryModelQuerySet:
        if info.context.user.is_authenticated:
            sort = info.context.GET.get('sort')
            je_qs = JournalEntryModel.objects.for_entity(
                    entity_slug=slug_name,
                    user_model=info.context.user
                ).for_ledger(ledger_pk=pk_ledger)
            if not sort:
                sort = '-updated'
                return je_qs.order_by(sort)
            else:
                raise NotImplementedError('Update the code to return the right value.')
                # This code would have originally returned None.  But logically it should probably return
                # the unsorted query, as below:
                # return je_qs
        else:
            return JournalEntryModel.objects.none()
