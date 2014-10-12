from __future__ import unicode_literals
import unittest

from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework import test

from nodeconductor.core.fields import comma_separated_string_list_re as ips_regex
from nodeconductor.cloud.tests import factories as cloud_factories
from nodeconductor.iaas.models import Instance
from nodeconductor.iaas.tests import factories
from nodeconductor.structure.models import ProjectRole
from nodeconductor.structure.tests import factories as structure_factories


class UrlResolverMixin(object):
    def _get_flavor_url(self, flavor):
        return 'http://testserver' + reverse('flavor-detail', kwargs={'uuid': flavor.uuid})

    def _get_project_url(self, project):
        return 'http://testserver' + reverse('project-detail', kwargs={'uuid': project.uuid})

    def _get_template_url(self, template):
        return 'http://testserver' + reverse('template-detail', kwargs={'uuid': template.uuid})

    def _get_instance_url(self, instance):
        return 'http://testserver' + reverse('instance-detail', kwargs={'uuid': instance.uuid})


class InstanceApiPermissionTest(UrlResolverMixin, test.APITransactionTestCase):
    def setUp(self):
        self.user = structure_factories.UserFactory.create()

        self.admined_instance = factories.InstanceFactory(state=Instance.States.OFFLINE)
        self.managed_instance = factories.InstanceFactory(state=Instance.States.OFFLINE)

        self.admined_instance.project.add_user(self.user, ProjectRole.ADMINISTRATOR)
        self.managed_instance.project.add_user(self.user, ProjectRole.MANAGER)

    # List filtration tests
    def test_anonymous_user_cannot_list_instances(self):
        response = self.client.get(reverse('instance-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_list_instances_of_projects_he_is_administrator_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse('instance-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        instance_url = self._get_instance_url(self.admined_instance)
        self.assertIn(instance_url, [instance['url'] for instance in response.data])

    def test_user_can_list_instances_of_projects_he_is_manager_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse('instance-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        instance_url = self._get_instance_url(self.managed_instance)
        self.assertIn(instance_url, [instance['url'] for instance in response.data])

    def test_user_cannot_list_instances_of_projects_he_has_no_role_in(self):
        self.client.force_authenticate(user=self.user)

        inaccessible_instance = factories.InstanceFactory()

        response = self.client.get(reverse('instance-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        instance_url = self._get_instance_url(inaccessible_instance)
        self.assertNotIn(instance_url, [instance['url'] for instance in response.data])

    # Direct instance access tests
    def test_anonymous_user_cannot_access_instance(self):
        instance = factories.InstanceFactory()
        response = self.client.get(self._get_instance_url(instance))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_access_instances_of_projects_he_is_administrator_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self._get_instance_url(self.admined_instance))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_can_access_instances_of_projects_he_is_manager_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self._get_instance_url(self.managed_instance))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_cannot_access_instances_of_projects_he_has_no_role_in(self):
        self.client.force_authenticate(user=self.user)

        inaccessible_instance = factories.InstanceFactory()

        response = self.client.get(self._get_project_url(inaccessible_instance))
        # 404 is used instead of 403 to hide the fact that the resource exists at all
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Deletion tests
    def test_anonymous_user_cannot_delete_instances(self):
        response = self.client.delete(self._get_project_url(factories.InstanceFactory()))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @unittest.skip('Requires extension via celery test runner')
    def test_user_cannot_delete_instances_of_projects_he_is_administrator_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(self._get_instance_url(self.admined_instance))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @unittest.skip('Requires extension via celery test runner')
    def test_user_cannot_delete_instances_of_projects_he_is_manager_of(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(self._get_instance_url(self.managed_instance))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Mutation tests
    def test_user_can_change_description_of_instance_he_is_administrator_of(self):
        self.client.force_authenticate(user=self.user)

        data = self._get_valid_payload(self.admined_instance)
        data['description'] = 'changed description1'

        response = self.client.put(self._get_instance_url(self.admined_instance), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        changed_instance = Instance.objects.get(pk=self.admined_instance.pk)

        self.assertEqual(changed_instance.description, 'changed description1')

    def test_user_cannot_change_description_of_instance_he_is_manager_of(self):
        self.client.force_authenticate(user=self.user)

        data = self._get_valid_payload(self.managed_instance)
        data['description'] = 'changed description1'

        response = self.client.put(self._get_instance_url(self.managed_instance), data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_change_description_of_instance_he_has_no_role_in(self):
        self.client.force_authenticate(user=self.user)

        inaccessible_instance = factories.InstanceFactory()
        data = self._get_valid_payload(inaccessible_instance)
        data['description'] = 'changed description1'

        response = self.client.put(self._get_instance_url(inaccessible_instance), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_change_description_single_field_of_instance_he_is_administrator_of(self):
        self.client.force_authenticate(user=self.user)

        data = {
            'description': 'changed description1',
        }

        response = self.client.patch(self._get_instance_url(self.admined_instance), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        changed_instance = Instance.objects.get(pk=self.admined_instance.pk)
        self.assertEqual(changed_instance.description, 'changed description1')

    def test_user_cannot_change_description_single_field__of_instance_he_is_manager_of(self):
        self.client.force_authenticate(user=self.user)

        data = {
            'description': 'changed description1',
        }

        response = self.client.patch(self._get_instance_url(self.managed_instance), data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_change_description_single_field_of_instance_he_has_no_role_in(self):
        self.client.force_authenticate(user=self.user)

        inaccessible_instance = factories.InstanceFactory()
        data = {
            'description': 'changed description1',
        }

        response = self.client.patch(self._get_instance_url(inaccessible_instance), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_change_flavor_of_stopped_instance_he_is_administrator_of(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        new_flavor = cloud_factories.FlavorFactory(cloud=self.admined_instance.flavor.cloud)

        data = {'flavor': str(new_flavor.uuid)}

        response = self.client.post(self._get_instance_url(self.admined_instance) + 'resize/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        changed_instance = Instance.objects.get(pk=self.admined_instance.pk)

        self.assertEqual(changed_instance.flavor, new_flavor)

    def test_user_cannot_change_flavor_of_stopped_instance_he_is_manager_of(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        new_flavor = cloud_factories.FlavorFactory(cloud=self.managed_instance.flavor.cloud)

        data = {'flavor': str(new_flavor.uuid)}

        response = self.client.post(self._get_instance_url(self.managed_instance) + 'resize/', data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_change_flavor_of_offline_instance_he_has_no_role_in(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        inaccessible_instance = factories.InstanceFactory()

        new_flavor = cloud_factories.FlavorFactory(cloud=inaccessible_instance.flavor.cloud)

        data = {'flavor': str(new_flavor.uuid)}

        response = self.client.post(self._get_instance_url(inaccessible_instance) + 'resize/', data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_change_flavor_of_running_instance_he_is_administrator_of(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        forbidden_states = {
            'starting': Instance.States.STARTING,
            'stopping': Instance.States.STOPPING,
            'online': Instance.States.ONLINE,
        }

        for state in forbidden_states.values():
            admined_instance = factories.InstanceFactory(state=state)

            admined_instance.project.add_user(self.user, ProjectRole.ADMINISTRATOR)

            changed_flavor = cloud_factories.FlavorFactory(cloud=admined_instance.flavor.cloud)

            data = {'flavor': str(changed_flavor.uuid)}

            response = self.client.post(self._get_instance_url(admined_instance) + 'resize/', data)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_change_flavor_of_running_instance_he_is_manager_of(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        forbidden_states = {
            'starting': Instance.States.STARTING,
            'stopping': Instance.States.STOPPING,
            'online': Instance.States.ONLINE,
        }

        for state in forbidden_states.values():
            managed_instance = factories.InstanceFactory(state=state)

            managed_instance.project.add_user(self.user, ProjectRole.ADMINISTRATOR)

            new_flavor = cloud_factories.FlavorFactory(cloud=managed_instance.flavor.cloud)

            data = {'flavor': str(new_flavor.uuid)}

            response = self.client.post(self._get_instance_url(managed_instance) + 'resize/', data)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_change_flavor_of_running_instance_he_has_no_role_in(self):
        self.skipTest('Requires extension via celery test runner')

        self.client.force_authenticate(user=self.user)

        forbidden_states = {
            'starting': Instance.States.STARTING,
            'stopping': Instance.States.STOPPING,
            'online': Instance.States.ONLINE,
        }

        for state in forbidden_states.values():
            inaccessible_instance = factories.InstanceFactory(state=state)

            new_flavor = cloud_factories.FlavorFactory(cloud=inaccessible_instance.flavor.cloud)

            data = {'flavor': str(new_flavor.uuid)}

            response = self.client.post(self._get_instance_url(inaccessible_instance) + 'resize/', data)

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Helpers method
    def _get_valid_payload(self, resource=None):
        resource = resource or factories.InstanceFactory()

        return {
            'hostname': resource.hostname,
            'description': resource.description,
            'project': self._get_project_url(resource.project),
            'template': self._get_template_url(resource.template),
            'flavor': self._get_flavor_url(resource.flavor),
        }

# XXX: What should happen to existing instances when their project is removed?


class InstanceProvisioningTest(UrlResolverMixin, test.APITransactionTestCase):
    def setUp(self):
        self.user = structure_factories.UserFactory.create()
        self.client.force_authenticate(user=self.user)

        self.instance_list_url = reverse('instance-list')

        cloud = cloud_factories.CloudFactory()

        self.template = factories.TemplateFactory()
        self.flavor = cloud_factories.FlavorFactory(cloud=cloud)
        self.project = structure_factories.ProjectFactory(cloud=cloud)

        self.project.add_user(self.user, ProjectRole.ADMINISTRATOR)

    # Assertions
    def assert_field_required(self, field_name):
        data = self.get_valid_data()
        del data[field_name]
        response = self.client.post(self.instance_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({field_name: ['This field is required.']}, response.data)

    def assert_field_non_empty(self, field_name, empty_value=''):
        data = self.get_valid_data()
        data[field_name] = empty_value
        response = self.client.post(self.instance_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({field_name: ['This field is required.']}, response.data)

    # Positive tests
    def test_can_create_instance_without_volume_sizes(self):
        data = self.get_valid_data()
        del data['volume_sizes']
        response = self.client.post(self.instance_list_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_can_create_instance_without_description(self):
        data = self.get_valid_data()
        del data['description']
        response = self.client.post(self.instance_list_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_can_create_instance_with_empty_description(self):
        data = self.get_valid_data()
        data['description'] = ''
        response = self.client.post(self.instance_list_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # TODO: Ensure that managers cannot provision instances
    # Negative tests
    def test_cannot_create_instance_with_flavor_not_from_supplied_project(self):
        data = self.get_valid_data()

        another_flavor = cloud_factories.FlavorFactory()
        another_project = structure_factories.ProjectFactory(
            cloud=another_flavor.cloud)

        another_project.add_user(self.user, ProjectRole.ADMINISTRATOR)

        data['flavor'] = self._get_flavor_url(another_flavor)

        response = self.client.post(self.instance_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'__all__': ["Flavor is not within project's clouds."]}, response.data)

    def test_cannot_create_instance_with_flavor_not_from_clouds_allowed_for_users_projects(self):
        data = self.get_valid_data()
        others_flavor = cloud_factories.FlavorFactory()
        data['flavor'] = self._get_flavor_url(others_flavor)

        response = self.client.post(self.instance_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'flavor': ['Invalid hyperlink - object does not exist.']}, response.data)

    def test_cannot_create_instance_with_project_not_from_users_projects(self):
        data = self.get_valid_data()
        others_project = structure_factories.ProjectFactory()
        data['project'] = self._get_project_url(others_project)

        response = self.client.post(self.instance_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'project': ['Invalid hyperlink - object does not exist.']}, response.data)

    def test_cannot_create_instance_with_empty_hostname_name(self):
        self.assert_field_non_empty('hostname')

    def test_cannot_create_instance_without_hostname_name(self):
        self.assert_field_required('hostname')

    def test_cannot_create_instance_with_empty_template_name(self):
        self.assert_field_non_empty('template')

    def test_cannot_create_instance_without_template_name(self):
        self.assert_field_required('template')

    def test_cannot_create_instance_without_flavor(self):
        self.assert_field_required('flavor')

    def test_cannot_create_instance_with_empty_flavor(self):
        self.assert_field_non_empty('flavor')

    def test_cannot_create_instance_with_negative_volume_size(self):
        self.skipTest("Not implemented yet")

        data = self.get_valid_data()
        data['volume_size'] = -12

        response = self.client.post(self.instance_list_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'volume_size': ['Ensure this value is greater than or equal to 1.']},
                                      response.data)

    def test_cannot_create_instance_with_invalid_volume_sizes(self):
        self.skipTest("Not implemented yet")

        data = self.get_valid_data()
        data['volume_sizes'] = 'gibberish'

        response = self.client.post(self.instance_list_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'volume_sizes': ['Enter a whole number.']},
                                      response.data)

    # instance ips field tests
    def test_instance_factory_generates_valid_ips_field(self):
        instance = factories.InstanceFactory()

        ips = instance.ips

        self.assertTrue(ips_regex.match(ips))

    def test_instance_api_contains_valid_ips_field(self):
        instance = factories.InstanceFactory()
        instance.project.add_user(self.user, ProjectRole.ADMINISTRATOR)

        response = self.client.get(self._get_instance_url(instance))

        ips = response.data['ips']

        for ip in ips:
            self.assertTrue(ips_regex.match(ip))

    # Helper methods
    def get_valid_data(self):
        return {
            # Cloud independent parameters
            'hostname': 'host1',
            'description': 'description1',

            # TODO: Make sure both project and flavor belong to the same customer
            'project': self._get_project_url(self.project),

            # Should not depend on cloud, instead represents an "aggregation" of templates
            'template': self._get_template_url(self.template),

            'volume_sizes': [10, 15, 10],

            # Cloud dependent parameters
            'flavor': self._get_flavor_url(self.flavor),
        }
