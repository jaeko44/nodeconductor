from __future__ import unicode_literals

import uuid

from django.contrib import auth
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models.functions import Concat
from django.utils import six
import django_filters
from django_filters.filterset import FilterSetMetaclass
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import BaseFilterBackend
import taggit

from nodeconductor.core import filters as core_filters
from nodeconductor.core import models as core_models
from nodeconductor.core.filters import BaseExternalFilter
from nodeconductor.logging.filters import ExternalAlertFilterBackend
from nodeconductor.structure import models
from nodeconductor.structure import SupportedServices
from nodeconductor.structure.managers import filter_queryset_for_user

User = auth.get_user_model()


class ScopeTypeFilterBackend(DjangoFilterBackend):
    """ Scope filters:

        * ?scope = ``URL``
        * ?scope_type = ``string`` (can be list)
    """

    content_type_field = 'content_type'
    scope_param = 'scope_type'
    scope_models = {
        'customer': models.Customer,
        'service': models.Service,
        'project': models.Project,
        'service_project_link': models.ServiceProjectLink,
        'resource': models.ResourceMixin
    }

    @classmethod
    def get_scope_type(cls, model):
        for scope_type, scope_model in cls.scope_models.items():
            if issubclass(model, scope_model):
                return scope_type

    @classmethod
    def _get_scope_models(cls, types):
        for scope_type, scope_model in cls.scope_models.items():
            if scope_type in types:
                try:
                    for submodel in scope_model.get_all_models():
                        yield submodel
                except AttributeError:
                    yield scope_model

    @classmethod
    def _get_scope_content_types(cls, types):
        return ContentType.objects.get_for_models(*cls._get_scope_models(types)).values()

    def filter_queryset(self, request, queryset, view):
        if self.scope_param in request.query_params:
            content_types = self._get_scope_content_types(request.query_params.getlist(self.scope_param))
            return queryset.filter(**{'%s__in' % self.content_type_field: content_types})
        return queryset


class GenericRoleFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return filter_queryset_for_user(queryset, request.user)


class GenericUserFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        user_uuid = request.query_params.get('user_uuid')
        if not user_uuid:
            return queryset

        try:
            uuid.UUID(user_uuid)
        except ValueError:
            return queryset.none()

        try:
            user = User.objects.get(uuid=user_uuid)
        except User.DoesNotExist:
            return queryset.none()

        return filter_queryset_for_user(queryset, user)


class CustomerFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr='icontains',
    )
    native_name = django_filters.CharFilter(
        lookup_expr='icontains',
    )
    abbreviation = django_filters.CharFilter(
        lookup_expr='icontains',
    )
    contact_details = django_filters.CharFilter(
        lookup_expr='icontains',
    )

    o = django_filters.OrderingFilter(
        fields=('name', 'abbreviation', 'contact_details', 'native_name', 'registration_code')
    )

    class Meta(object):
        model = models.Customer
        fields = [
            'name',
            'abbreviation',
            'contact_details',
            'native_name',
            'registration_code',
        ]


class ProjectFilter(django_filters.FilterSet):
    customer = django_filters.UUIDFilter(
        name='customer__uuid',
        distinct=True,
    )

    customer_name = django_filters.CharFilter(
        name='customer__name',
        distinct=True,
        lookup_expr='icontains'
    )

    customer_native_name = django_filters.CharFilter(
        name='customer__native_name',
        distinct=True,
        lookup_expr='icontains'
    )

    customer_abbreviation = django_filters.CharFilter(
        name='customer__abbreviation',
        distinct=True,
        lookup_expr='icontains'
    )

    name = django_filters.CharFilter(lookup_expr='icontains')

    description = django_filters.CharFilter(lookup_expr='icontains')

    o = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('created', 'created'),
            ('customer__name', 'customer_name'),
            ('customer__native_name', 'customer_native_name'),
            ('customer__abbreviation', 'customer_abbreviation'),
        )
    )

    class Meta(object):
        model = models.Project
        fields = [
            'name',
            'customer', 'customer_name', 'customer_native_name', 'customer_abbreviation',
            'description',
            'created',
        ]


class CustomerUserFilter(DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        customer_uuid = request.query_params.get('customer_uuid')
        if not customer_uuid:
            return queryset

        try:
            uuid.UUID(customer_uuid)
        except ValueError:
            return queryset.none()

        return queryset.filter(
            Q(customerpermission__customer__uuid=customer_uuid,
              customerpermission__is_active=True) |
            Q(projectpermission__project__customer__uuid=customer_uuid,
              projectpermission__is_active=True)
        ).distinct()


class ProjectUserFilter(DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        project_uuid = request.query_params.get('project_uuid')
        if not project_uuid:
            return queryset

        try:
            uuid.UUID(project_uuid)
        except ValueError:
            return queryset.none()

        return queryset.filter(
            projectpermission__project__uuid=project_uuid,
            projectpermission__is_active=True
        ).distinct()


class UserFilter(django_filters.FilterSet):
    full_name = django_filters.CharFilter(lookup_expr='icontains')
    username = django_filters.CharFilter()
    native_name = django_filters.CharFilter(lookup_expr='icontains')
    job_title = django_filters.CharFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    o = django_filters.OrderingFilter(
        fields=('full_name', 'native_name', 'organization',
                'organization_approved', 'email', 'phone_number',
                'description', 'job_title', 'username',
                'is_active', 'registration_method')
    )

    class Meta(object):
        model = User
        fields = [
            'full_name',
            'native_name',
            'organization',
            'organization_approved',
            'email',
            'phone_number',
            'description',
            'job_title',
            'username',
            'civil_number',
            'is_active',
            'registration_method',
        ]


class UserConcatenatedNameOrderingBackend(DjangoFilterBackend):
    """ Filter user by concatenated full_name + username with ?o=concatenated_name """
    def filter_queryset(self, request, queryset, view):
        if 'o' not in request.query_params:
            return queryset
        if request.query_params['o'] == 'concatenated_name':
            order_by = 'concatenated_name'
        elif request.query_params['o'] == '-concatenated_name':
            order_by = '-concatenated_name'
        else:
            return queryset
        return queryset.annotate(concatenated_name=Concat('full_name', 'username')).order_by(order_by)


class UserPermissionFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter(name='user__uuid')
    user_url = core_filters.URLFilter(
        view_name='user-detail',
        name='user__uuid',
    )
    username = django_filters.CharFilter(
        name='user__username',
        lookup_expr='exact',
    )
    full_name = django_filters.CharFilter(
        name='user__full_name',
        lookup_expr='icontains',
    )
    native_name = django_filters.CharFilter(
        name='user__native_name',
        lookup_expr='icontains',
    )

    o = django_filters.OrderingFilter(
        fields=(
            ('user__username', 'username'),
            ('user__full_name', 'full_name'),
            ('user__native_name', 'native_name'),
            ('user__email', 'email'),
            ('expiration_time', 'expiration_time'),
            ('created', 'created'),
            ('role', 'role'),
        )
    )


class ProjectPermissionFilter(UserPermissionFilter):
    class Meta(object):
        fields = ['role']
        model = models.ProjectPermission

    customer = django_filters.UUIDFilter(
        name='project__customer__uuid',
    )
    project = django_filters.UUIDFilter(
        name='project__uuid',
    )
    project_url = core_filters.URLFilter(
        view_name='project-detail',
        name='project__uuid',
    )


class CustomerPermissionFilter(UserPermissionFilter):
    class Meta(object):
        fields = ['role']
        model = models.CustomerPermission

    customer = django_filters.UUIDFilter(
        name='customer__uuid',
    )
    customer_url = core_filters.URLFilter(
        view_name='customer-detail',
        name='customer__uuid',
    )


class SshKeyFilter(django_filters.FilterSet):
    uuid = django_filters.UUIDFilter()
    user_uuid = django_filters.UUIDFilter(name='user__uuid')
    name = django_filters.CharFilter(lookup_expr='icontains')

    o = django_filters.OrderingFilter(fields=('name',))

    class Meta(object):
        model = core_models.SshPublicKey
        fields = [
            'name',
            'fingerprint',
            'uuid',
            'user_uuid',
            'is_shared',
        ]


class ServiceTypeFilter(django_filters.Filter):
    def filter(self, qs, value):
        value = SupportedServices.get_filter_mapping().get(value)
        return super(ServiceTypeFilter, self).filter(qs, value)


class ServiceSettingsFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    type = ServiceTypeFilter()
    state = core_filters.StateFilter()

    class Meta(object):
        model = models.ServiceSettings
        fields = ('name', 'type', 'state', 'shared')


class ServiceSettingsScopeFilterBackend(core_filters.GenericKeyFilterBackend):

    def get_related_models(self):
        return models.ResourceMixin.get_all_models()

    def get_field_name(self):
        return 'scope'


class ServiceFilterMetaclass(FilterSetMetaclass):
    """ Build a list of supported resource via serializers definition.
        See SupportedServices for details.
    """
    def __new__(mcs, name, bases, args):
        service_filter = super(ServiceFilterMetaclass, mcs).__new__(mcs, name, bases, args)
        model = args['Meta'].model
        if not model._meta.abstract:
            SupportedServices.register_service_filter(args['Meta'].model, service_filter)
        return service_filter


class BaseServiceFilter(six.with_metaclass(ServiceFilterMetaclass, django_filters.FilterSet)):
    customer = django_filters.UUIDFilter(name='customer__uuid')
    name = django_filters.CharFilter(name='settings__name', lookup_expr='icontains')
    name_exact = django_filters.CharFilter(name='settings__name', lookup_expr='exact')
    project = core_filters.URLFilter(view_name='project-detail', name='projects__uuid', distinct=True)
    project_uuid = django_filters.UUIDFilter(name='projects__uuid', distinct=True)
    settings = core_filters.URLFilter(view_name='servicesettings-detail', name='settings__uuid', distinct=True)
    shared = django_filters.BooleanFilter(name='settings__shared', distinct=True)
    type = ServiceTypeFilter(name='settings__type')
    tag = django_filters.ModelMultipleChoiceFilter(
        name='settings__tags__name',
        to_field_name='name',
        lookup_expr='in',
        queryset=taggit.models.Tag.objects.all(),
    )
    # rtag - required tag, support for filtration by tags using AND operation
    # ?rtag=t1&rtag=t2 - will filter instances that have both t1 and t2.
    rtag = django_filters.ModelMultipleChoiceFilter(
        name='settings__tags__name',
        to_field_name='name',
        queryset=taggit.models.Tag.objects.all(),
        conjoined=True,
    )

    class Meta(object):
        model = models.Service
        fields = ('name', 'name_exact', 'project_uuid', 'customer', 'project', 'settings', 'shared', 'type', 'tag', 'rtag')


class BaseServiceProjectLinkFilter(django_filters.FilterSet):
    service_uuid = django_filters.UUIDFilter(name='service__uuid')
    customer_uuid = django_filters.UUIDFilter(name='service__customer__uuid')
    project_uuid = django_filters.UUIDFilter(name='project__uuid')
    project = core_filters.URLFilter(view_name='project-detail', name='project__uuid')

    class Meta(object):
        model = models.ServiceProjectLink
        fields = ()


class ResourceFilterMetaclass(FilterSetMetaclass):
    """ Build a list of supported resource via serializers definition.
        See SupportedServices for details.
    """
    def __new__(cls, name, bases, args):
        resource_filter = super(ResourceFilterMetaclass, cls).__new__(cls, name, bases, args)
        SupportedServices.register_resource_filter(args['Meta'].model, resource_filter)
        return resource_filter


class BaseResourceFilter(six.with_metaclass(ResourceFilterMetaclass,
                         django_filters.FilterSet)):
    def __init__(self, *args, **kwargs):
        super(BaseResourceFilter, self).__init__(*args, **kwargs)
        self.filters['o'] = django_filters.OrderingFilter(fields=self.ORDERING_FIELDS)

    # customer
    customer = django_filters.UUIDFilter(name='service_project_link__service__customer__uuid')
    customer_uuid = django_filters.UUIDFilter(name='service_project_link__service__customer__uuid')
    customer_name = django_filters.CharFilter(
        name='service_project_link__service__customer__name', lookup_expr='icontains')
    customer_native_name = django_filters.CharFilter(
        name='service_project_link__project__customer__native_name', lookup_expr='icontains')
    customer_abbreviation = django_filters.CharFilter(
        name='service_project_link__project__customer__abbreviation', lookup_expr='icontains')
    # project
    project = django_filters.UUIDFilter(name='service_project_link__project__uuid')
    project_uuid = django_filters.UUIDFilter(name='service_project_link__project__uuid')
    project_name = django_filters.CharFilter(name='service_project_link__project__name', lookup_expr='icontains')
    # service
    service_uuid = django_filters.UUIDFilter(name='service_project_link__service__uuid')
    service_name = django_filters.CharFilter(name='service_project_link__service__settings__name', lookup_expr='icontains')
    # service settings
    service_settings_uuid = django_filters.UUIDFilter(name='service_project_link__service__settings__uuid')
    service_settings_name = django_filters.CharFilter(name='service_project_link__service__settings__name',
                                                      lookup_expr='icontains')
    # resource
    name = django_filters.CharFilter(lookup_expr='icontains')
    name_exact = django_filters.CharFilter(name='name', lookup_expr='exact')
    description = django_filters.CharFilter(lookup_expr='icontains')
    state = core_filters.MappedMultipleChoiceFilter(
        choices=[(representation, representation) for db_value, representation in core_models.StateMixin.States.CHOICES],
        choice_mappings={representation: db_value for db_value, representation in core_models.StateMixin.States.CHOICES},
    )
    uuid = django_filters.UUIDFilter(lookup_expr='exact')
    tag = django_filters.ModelMultipleChoiceFilter(
        name='tags__name',
        label='tag',
        to_field_name='name',
        lookup_expr='in',
        queryset=taggit.models.Tag.objects.all(),
    )
    rtag = django_filters.ModelMultipleChoiceFilter(
        name='tags__name',
        label='rtag',
        to_field_name='name',
        queryset=taggit.models.Tag.objects.all(),
        conjoined=True,
    )

    ORDERING_FIELDS = (
        ('name', 'name'),
        ('state', 'state'),
        ('service_project_link__project__customer__name', 'customer_name'),
        ('service_project_link__project__customer__native_name', 'customer_native_name'),
        ('service_project_link__project__customer__abbreviation', 'customer_abbreviation'),
        ('service_project_link__project__name', 'project_name'),
        ('service_project_link__service__settings__name', 'service_name'),
        ('service_project_link__service__uuid', 'service_uuid'),
        ('created', 'created'),
    )

    class Meta(object):
        model = models.ResourceMixin
        fields = (
            # customer
            'customer', 'customer_uuid', 'customer_name', 'customer_native_name', 'customer_abbreviation',
            # project
            'project', 'project_uuid', 'project_name',
            # service
            'service_uuid', 'service_name',
            # service settings
            'service_settings_name', 'service_settings_uuid',
            # resource
            'name', 'name_exact', 'description', 'state', 'uuid', 'tag', 'rtag',
        )


class TagsFilter(BaseFilterBackend):
    """ Tags ordering. Filtering for complex tags.

    Example:
        ?tag__license-os=centos7 - will filter objects with tag "license-os:centos7".

    Allow to define next parameters in view:
     - tags_filter_db_field - name of tags field in database. Default: tags.
     - tags_filter_request_field - name of tags in request. Default: tag.
    """

    def filter_queryset(self, request, queryset, view):
        self.db_field = getattr(view, 'tags_filter_db_field', 'tags')
        self.request_field = getattr(view, 'tags_filter_request_field', 'tag')

        queryset = self._filter(request, queryset)
        queryset = self._order(request, queryset)
        return queryset

    def _filter(self, request, queryset):
        for key in request.query_params.keys():
            item_name = self._get_item_name(key)
            if item_name:
                value = request.query_params.get(key)
                filter_kwargs = {
                    self.db_field + '__name__startswith': item_name,
                    self.db_field + '__name__icontains': value,
                }
                queryset = queryset.filter(**filter_kwargs)
        return queryset

    def _order(self, request, queryset):
        order_by = request.query_params.get('o')
        item_name = self._get_item_name(order_by)
        if item_name:
            filter_kwargs = {self.db_field + '__name__startswith': item_name}
            queryset = queryset.filter(**filter_kwargs).order_by(self.db_field + '__name')
        return queryset

    def _get_item_name(self, key):
        prefix = self.request_field + '__'
        if key and key.startswith(prefix):
            return key[len(prefix):]


class StartTimeFilter(BaseFilterBackend):
    """
    In PostgreSQL NULL values come *last* with ascending sort order.
    In MySQL NULL values come *first* with ascending sort order.
    This filter provides unified sorting for both databases.
    """
    def filter_queryset(self, request, queryset, view):
        order = request.query_params.get('o', None)
        if order == 'start_time':
            queryset = queryset.extra(select={
                'is_null': 'CASE WHEN start_time IS NULL THEN 0 ELSE 1 END'}) \
                .order_by('is_null', 'start_time')
        elif order == '-start_time':
            queryset = queryset.extra(select={
                'is_null': 'CASE WHEN start_time IS NULL THEN 0 ELSE 1 END'}) \
                .order_by('-is_null', '-start_time')

        return queryset


class BaseServicePropertyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(name='name', lookup_expr='icontains')
    name_exact = django_filters.CharFilter(name='name', lookup_expr='exact')

    class Meta(object):
        fields = ('name', 'name_exact')


class ServicePropertySettingsFilter(BaseServicePropertyFilter):
    settings_uuid = django_filters.UUIDFilter(name='settings__uuid')
    settings = core_filters.URLFilter(view_name='servicesettings-detail', name='settings__uuid', distinct=True)

    class Meta(BaseServicePropertyFilter.Meta):
        fields = BaseServicePropertyFilter.Meta.fields + ('settings_uuid', 'settings')


class AggregateFilter(BaseExternalFilter):
    """
    Filter by aggregate
    """

    def filter(self, request, queryset, view):
        # Don't apply filter if aggregate is not specified
        if 'aggregate' not in request.query_params:
            return queryset

        aggregate = request.query_params['aggregate']
        uuid = request.query_params.get('uuid')

        return filter_alerts_by_aggregate(queryset, aggregate, request.user, uuid)


def filter_alerts_by_aggregate(queryset, aggregate, user, uuid=None):
    valid_model_choices = {
        'project': models.Project,
        'customer': models.Customer,
    }

    error = '"%s" parameter is not found. Valid choices are: %s.' % (aggregate, ', '.join(valid_model_choices.keys()))
    assert (aggregate in valid_model_choices), error

    aggregate_query = filter_queryset_for_user(valid_model_choices[aggregate].objects, user)

    if uuid:
        aggregate_query = aggregate_query.filter(uuid=uuid)

    aggregates_ids = aggregate_query.values_list('id', flat=True)
    query = {'%s__in' % aggregate: aggregates_ids}

    all_models = models.ResourceMixin.get_all_models() + models.ServiceProjectLink.get_all_models()
    if aggregate == 'customer':
        all_models += models.Service.get_all_models()
        all_models.append(models.Project)

    querysets = [aggregate_query]
    for model in all_models:
        qs = model.objects.filter(**query).all()
        querysets.append(filter_queryset_for_user(qs, user))

    aggregate_query = Q()
    for qs in querysets:
        content_type = ContentType.objects.get_for_model(qs.model)
        ids = qs.values_list('id', flat=True)
        aggregate_query |= Q(content_type=content_type, object_id__in=ids)

    return queryset.filter(aggregate_query)

ExternalAlertFilterBackend.register(AggregateFilter())


class ResourceSummaryFilterBackend(core_filters.SummaryFilter):
    """ Filter and order SummaryQuerySet of resources """

    def get_queryset_filter(self, queryset):
        try:
            return SupportedServices.get_resource_filter(queryset.model)
        except KeyError:
            return super(ResourceSummaryFilterBackend, self).get_queryset_filter(queryset)

    def get_base_filter(self):
        return BaseResourceFilter


class ServiceSummaryFilterBackend(core_filters.SummaryFilter):

    def get_queryset_filter(self, queryset):
        try:
            return SupportedServices.get_service_filter(queryset.model)
        except KeyError:
            return super(ServiceSummaryFilterBackend, self).get_queryset_filter(queryset)

    def get_base_filter(self):
        return BaseServiceFilter
