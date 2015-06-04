import time

from rest_framework import serializers
from rest_framework.exceptions import ParseError

from nodeconductor.logging import models, utils
from nodeconductor.core.serializers import GenericRelatedField
from nodeconductor.core.fields import MappedChoiceField, JsonField
from nodeconductor.core.utils import timestamp_to_datetime


class AlertSerializer(serializers.HyperlinkedModelSerializer):
    scope = GenericRelatedField(related_models=utils.get_loggable_models(), read_only=True)
    severity = MappedChoiceField(
        choices=[(v, k) for k, v in models.Alert.SeverityChoices.CHOICES],
        choice_mappings={v: k for k, v in models.Alert.SeverityChoices.CHOICES},
        read_only=True,
    )
    context = JsonField()

    class Meta(object):
        model = models.Alert
        fields = ('url', 'uuid', 'alert_type', 'message', 'severity', 'scope', 'created', 'closed', 'context')
        read_only_fields = ('uuid', 'created', 'closed')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }


class StatsQuerySerializer(serializers.Serializer):
    def get_alerts(self, request):
        alerts = models.Alert.objects.filtered_for_user(request.user)\
                                     .filter(closed__isnull=True)

        if 'from' in request.query_params:
            day = 60 * 60 * 24
            start_timestamp = request.query_params.get('from', int(time.time() - day))
            start_datetime = self.parse_timestamp(start_timestamp)
            alerts = alerts.filter(created__gte=start_datetime)

        if 'to' in request.query_params:
            end_timestamp = request.query_params.get('to', int(time.time()))
            end_datetime = self.parse_timestamp(end_timestamp)
            alerts = alerts.filter(created__lte=end_datetime)

        return alerts

    def parse_timestamp(self, timestamp):
        try:
            return timestamp_to_datetime(timestamp)
        except ValueError:
            raise ParseError("Invalid timestamp")
