from types import SimpleNamespace
from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class ObjectSetTests(TestCase):
    def test_assigns_an_attribute_and_reads_the_updated_value(self):
        person = SimpleNamespace(name='before')
        template = Template("#set($person.name = 'after')$person.name")
        self.assertEqual(template.merge({'person': person}), 'after')
        self.assertEqual(person.name, 'after')

    def test_traverses_objects_and_mappings_in_both_directions(self):
        person = SimpleNamespace(details={'address': SimpleNamespace(city='old')})
        template = Template("#set($person.details.address.city = 'new')"
                            "$person.details.address.city")
        self.assertEqual(template.merge({'person': person}), 'new')
        self.assertEqual(person.details['address'].city, 'new')

    def test_assigns_a_dictionary_entry_reached_through_an_object(self):
        person = SimpleNamespace(details={})
        template = Template("#set($person.details.name = 'new')$person.details.name")
        self.assertEqual(template.merge({'person': person}), 'new')
        self.assertEqual(person.details, {'name': 'new'})

    def test_preserves_custom_mapping_item_access(self):
        class Mapping:
            def __init__(self, items):
                self.items = items

            def __getitem__(self, key):
                return self.items[key]

            def __setitem__(self, key, value):
                self.items[key] = value

        inner = Mapping({'name': 'old'})
        outer = Mapping({'inner': inner})
        template = Template("#set($outer.inner.name = 'new')$outer.inner.name")
        self.assertEqual(template.merge({'outer': outer}), 'new')
        self.assertEqual(inner.items['name'], 'new')
        self.assertNotIn('name', vars(inner))

    def test_does_not_hide_mapping_assignment_errors(self):
        class Mapping:
            def __setitem__(self, key, value):
                raise TypeError('read only')

        mapping = Mapping()
        with self.assertRaises(TemplateExecutionError) as caught:
            Template('#set($item.name = 1)').merge({'item': mapping})
        self.assertIsInstance(caught.exception.__cause__, TypeError)
        self.assertNotIn('name', vars(mapping))

    def test_uses_property_setters_and_preserves_their_errors(self):
        class Person:
            @property
            def name(self):
                return self._name

            @name.setter
            def name(self, value):
                if not value:
                    raise ValueError('name cannot be empty')
                self._name = value.upper()

        person = Person()
        template = Template("#set($person.name = 'new')$person.name")
        self.assertEqual(template.merge({'person': person}), 'NEW')
        with self.assertRaises(TemplateExecutionError) as caught:
            Template("#set($person.name = '')").merge({'person': person})
        self.assertIsInstance(caught.exception.__cause__, ValueError)
