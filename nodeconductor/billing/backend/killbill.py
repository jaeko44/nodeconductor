import re
import json
import requests
import logging

from datetime import datetime
from lxml.builder import E, ElementMaker
from lxml import etree

from django.contrib.contenttypes.models import ContentType

from nodeconductor.cost_tracking import CostConstants
from nodeconductor.cost_tracking.models import DefaultPriceListItem, ResourceUsage
from nodeconductor.billing.backend import BillingBackendError
from nodeconductor import __version__


logger = logging.getLogger(__name__)


class KillBillAPI(object):
    """ Killbill API client -- http://killbill.io/api/
        Test settings:

            NODECONDUCTOR['BILLING'] = {
                'backend': 'nodeconductor.billing.backend.killbill.KillBillAPI',
                'api_url': 'http://killbill.example.com:8080/1.0/kb/',
                'username': 'admin',
                'password': 'password',
                'api_key': 'bob',
                'api_secret': 'lazar',
            }
    """

    def __init__(self, api_url=None, username=None, password=None, api_key=None, api_secret=None, **kwargs):
        if not all((api_url, api_key, api_secret)):
            raise BillingBackendError(
                "Missed billing credentials. They must be supplied explicitly "
                "or defined within settings.NODECONDUCTOR.BILLING")

        self.currency = 'USD'
        self.credentials = dict(
            api_url=api_url,
            api_key=api_key,
            api_secret=api_secret,
            auth=(username, password))

        self.accounts = KillBill.Account(self.credentials)
        self.catalog = KillBill.Catalog(self.credentials)
        self.invoices = KillBill.Invoice(self.credentials)
        self.subscriptions = KillBill.Subscription(self.credentials)
        self.usages = KillBill.Usage(self.credentials)
        self.test = KillBill.Test(self.credentials)

    def _get_plan_name_for_content_type(self, content_type):
        return "{}-{}".format(content_type.app_label, content_type.model)

    def _get_product_name_for_content_type(self, content_type):
        return self._get_plan_name_for_content_type(content_type).title().replace('-', '')

    def add_client(self, name=None, uuid=None, **kwargs):
        account = self.accounts.create(
            name=name, externalKey=uuid, currency=self.currency)
        return account['accountId']

    def get_client_details(self, client_id):
        account = self.accounts.get(client_id)
        return {'balance': account['accountBalance']}

    def get_client_by_uuid(self, uuid):
        return self.accounts.list(externalKey=uuid)

    def add_subscription(self, client_id, resource):
        content_type = ContentType.objects.get_for_model(resource)
        product_name = self._get_product_name_for_content_type(content_type)
        subscription = self.subscriptions.create(
            productName=product_name,
            productCategory='STANDALONE',
            accountId=client_id,
            externalKey=resource.uuid.hex,
            billingPeriod='MONTHLY',
            priceList='DEFAULT')

        return subscription['subscriptionId']

    def del_subscription(self, subscription_id):
        self.subscriptions.delete(subscription_id)

    def add_usage(self, resource):
        # Push info about current resource configuration to backend
        # otherwise be called once a day and submit daily usage
        # http://docs.killbill.io/0.14/consumable_in_arrear.html#_usage_and_metering

        today = datetime.utcnow().date()
        content_type = ContentType.objects.get_for_model(resource)
        usage_qs = ResourceUsage.objects.filter(
            date=today,
            content_type=content_type,
            object_id=resource.id)

        records = []
        for usage in usage_qs:
            records.append({
                'unitType': usage.units,
                'usageRecords': [{
                    'recordDate': today.strftime('%Y-%m-%d'),
                    'amount': str(usage.value),
                }],
            })

        self.usages.create(subscriptionId=resource.billing_backend_id, unitUsageRecords=records)

    def get_dry_invoice(self, client_id, date=None):
        if not date:
            date = datetime.utcnow().date()

        return self.invoices.request(
            'invoices/dryRun',
            method='POST',
            accountId=client_id,
            targetDate=date.strftime('%Y-%m-%d'))

    def get_invoice_items(self, invoice_id):
        raise NotImplementedError

    def create_invoice(self, data):
        raise NotImplementedError

    def propagate_pricelist(self):
        # Generate catalog and push it to backend
        # http://killbill.github.io/killbill-docs/0.15/userguide_subscription.html#components-catalog

        plans = E.plans()
        prods = E.products()
        units = set()
        plannames = []

        priceitems = DefaultPriceListItem.objects.values_list('resource_content_type', flat=True).distinct()
        for cid in priceitems:
            content_type = ContentType.objects.get_for_id(cid)
            plan_name = self._get_plan_name_for_content_type(content_type)
            product_name = self._get_product_name_for_content_type(content_type)

            usages = E.usages()
            for priceitem in DefaultPriceListItem.objects.filter(resource_content_type=cid):
                usage_name = re.sub(r'[\s:;,+%&$@/]+', '', "{}-{}".format(priceitem.item_type, priceitem.key))
                unit_name = "hour-of-%s" % usage_name
                usage = E.usage(
                    E.billingPeriod('MONTHLY'),
                    E.tiers(E.tier(E.blocks(E.tieredBlock(
                        E.unit(unit_name),
                        E.size('1'),
                        E.prices(E.price(
                            E.currency(self.currency),
                            E.value(str(priceitem.value)),
                        )),
                        E.max('744'),  # max hours in a month
                    )))),
                    name=usage_name,
                    billingMode='IN_ARREAR',
                    usageType='CONSUMABLE')

                usages.append(usage)
                units.add(unit_name)

                priceitem.units = unit_name
                priceitem.save(update_fields=['units'])

            plan = E.plan(
                E.product(product_name),
                E.finalPhase(
                    E.duration(E.unit('UNLIMITED')),
                    E.recurring(  # recurring must be defined event if it's not used
                        E.billingPeriod('MONTHLY'),
                        E.recurringPrice(E.price(
                            E.currency(self.currency),
                            E.value('0'),
                        )),
                    ),
                    usages,
                    type='EVERGREEN'),
                name=plan_name)

            prods.append(E.product(E.category('STANDALONE'), name=product_name))

            plans.append(plan)
            plannames.append(plan_name)

        xsi = 'http://www.w3.org/2001/XMLSchema-instance'
        catalog = ElementMaker(nsmap={'xsi': xsi}).catalog(
            E.effectiveDate(datetime.utcnow().isoformat("T")),
            E.catalogName('NodeConductor'),
            E.recurringBillingMode('IN_ADVANCE'),
            E.currencies(E.currency(self.currency)),
            E.units(*[E.unit(name=u) for u in units]),
            prods,
            E.rules(
                E.changePolicy(E.changePolicyCase(E.policy('END_OF_TERM'))),
                E.changeAlignment(E.changeAlignmentCase(E.alignment('START_OF_SUBSCRIPTION'))),
                E.cancelPolicy(
                    E.cancelPolicyCase(E.productCategory('STANDALONE'), E.policy('END_OF_TERM')),
                    E.cancelPolicyCase(E.policy('END_OF_TERM')),
                ),
                E.billingAlignment(E.billingAlignmentCase(E.alignment('ACCOUNT'))),
                E.priceList(E.priceListCase(E.toPriceList('DEFAULT'))),
            ),
            plans,
            E.priceLists(E.defaultPriceList(E.plans(*[E.plan(n) for n in plannames]), name='DEFAULT')),
            **{'{{{}}}schemaLocation'.format(xsi): 'CatalogSchema.xsd'})

        xml = etree.tostring(
            catalog, xml_declaration=True, pretty_print=True, standalone=False, encoding='UTF-8')

        self.catalog.create(xml)

    def get_total_cost_of_active_products(self, client_id):
        # TODO (NC-738)
        raise NotImplementedError

    def get_client_orders(self, client_id):
        raise NotImplementedError


class KillBill(object):

    class BaseResource(object):
        path = NotImplemented
        type = 'application/json'

        def __init__(self, credentials):
            self.__dict__ = credentials

        def __repr__(self):
            return self.api_url + self.path

        def list(self, **kwargs):
            return self.request(self.path, method='GET', **kwargs)

        def get(self, uuid, entity=None, **kwargs):
            return self.request('/'.join([self.path, uuid, entity or '']), method='GET', **kwargs)

        def create(self, raw_data=None, **kwargs):
            data = raw_data or json.dumps(kwargs)
            return self.request(self.path, method='POST', data=data)

        def delete(self, uuid):
            return self.request('/'.join([self.path, uuid]), method='DELETE')

        def request(self, url, method='GET', data=None, **kwargs):
            response_types = {'application/json': 'json', 'application/xml': 'xml'}
            headers = {'User-Agent': 'NodeConductor/%s' % __version__,
                       'Accept': 'application/json',
                       'X-Killbill-ApiKey': self.api_key,
                       'X-Killbill-ApiSecret': self.api_secret}

            if method.upper() in ('POST', 'DELETE'):
                headers['Content-Type'] = self.type
                headers['X-Killbill-CreatedBy'] = 'NodeConductor'

            url = url if url.startswith(self.api_url) else self.api_url + url
            response = getattr(requests, method.lower())(
                url, params=kwargs, data=data, auth=self.auth, headers=headers)

            codes = requests.status_codes.codes
            response_type = response_types.get(response.headers.get('content-type'), '')

            if response.status_code == codes.created:
                location = response.headers.get('location')
                if location:
                    return self.request(location)

            elif response.status_code != codes.ok:
                reason = response.reason
                if response_type == 'json':
                    try:
                        reason = response.json()['message']
                    except ValueError:
                        pass
                elif response.status_code == codes.server_error:
                    try:
                        txt = etree.fromstring(response.text)
                        reason = txt.xpath('.//pre/text()')[1].split('\n')[2]
                    except ValueError:
                        pass

                raise BillingBackendError(
                    "%s. Request to Killbill backend failed: %s" % (response.status_code, reason))

            try:
                if response_type == 'xml':
                    data = etree.fromstring(
                        response.text.encode('utf-8'),
                        etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8'))

                elif response_type == 'json' and response.text:
                    data = response.json()

                else:
                    data = response.text

            except ValueError as e:
                raise BillingBackendError(
                    "Incorrect response from Killbill backend %s: %s" % (url, e))

            return data

    class Account(BaseResource):
        path = 'accounts'

    class Catalog(BaseResource):
        path = 'catalog'
        type = 'application/xml'

    class Invoice(BaseResource):
        path = 'invoices'

    class Subscription(BaseResource):
        path = 'subscriptions'

    class Test(BaseResource):
        path = 'test/clock'

    class Usage(BaseResource):
        path = 'usages'
