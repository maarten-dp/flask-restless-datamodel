from datetime import date
from unittest.mock import patch

import cereal_lazer as sr
import flask_restless
import pytest
from flask_restless_datamodel import DataModel
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property


def test_datamodel(app, client_maker):
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        birth_date = db.Column(db.Date)

    class Computer(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        vendor = db.Column(db.Unicode)
        purchase_time = db.Column(db.DateTime)
        owner_id = db.Column(db.Integer, db.ForeignKey('person.id'))
        owner = db.relationship(
            'Person', backref=db.backref('computers', lazy='dynamic'))
        owner_name = association_proxy('owner', 'name')
        peers = association_proxy('owner', 'computers')

    db.create_all()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'], include_columns=['name'])
    data_model = DataModel(manager)
    manager.create_api(data_model, methods=['GET'])
    manager.create_api(
        Computer,
        methods=['GET'],
        collection_name='compjutahs',
        exclude_columns=['name'])

    expected = {
        'Computer': {
            'pk_name': 'id',
            'collection_name': 'compjutahs',
            'attributes': {
                'id': 'integer',
                'owner_id': 'integer',
                'owner_name': 'unicode',
                'purchase_time': 'datetime',
                'vendor': 'unicode'
            },
            'relations': {
                'owner': {
                    'backref': 'computers',
                    'foreign_model': 'Person',
                    'local_column': 'owner_id',
                    'relation_type': 'MANYTOONE'
                },
                'peers': {
                    'foreign_model': 'Computer',
                    'is_proxy': True,
                    'relation_type': 'MANYTOONE'
                }
            },
            'properties': {},
            'methods': {}
        },
        'Person': {
            'pk_name': 'id',
            'collection_name': 'person',
            'attributes': {
                'name': 'unicode'
            },
            'relations': {},
            'properties': {},
            'methods': {}
        }
    }

    client = client_maker(app)
    res = client.get('http://app/api/flask-restless-datamodel').json()
    assert res == expected


def test_inheritance(app, client_maker):
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        discriminator = db.Column(db.Unicode)
        __mapper_args__ = {'polymorphic_on': discriminator}

    class Engineer(Person):
        __mapper_args__ = {'polymorphic_identity': 'engineer'}
        id = db.Column(
            db.Integer, db.ForeignKey('person.id'), primary_key=True)
        primary_language = db.Column(db.Unicode)

    db.create_all()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'])
    manager.create_api(Engineer, methods=['GET'])
    data_model = DataModel(manager)
    manager.create_api(data_model, methods=['GET'])

    expected = {
        'Engineer': {
            'pk_name': 'id',
            'collection_name': 'engineer',
            'polymorphic': {
                'identity': 'engineer',
                'parent': 'Person',
            },
            'attributes': {
                'id': 'integer',
                'primary_language': 'unicode',
                'discriminator': 'unicode'
            },
            'relations': {},
            'properties': {},
            'methods': {}
        },
        'Person': {
            'pk_name': 'id',
            'collection_name': 'person',
            'polymorphic': {
                'on': 'discriminator',
                'identities': {
                    'engineer': 'Engineer'
                }
            },
            'attributes': {
                'id': 'integer',
                'discriminator': 'unicode'
            },
            'relations': {},
            'properties': {},
            'methods': {}
        }
    }

    client = client_maker(app)
    res = client.get('http://app/api/flask-restless-datamodel').json()
    assert res == expected


@pytest.fixture(scope='function')
def exposed_method_model_app(app):
    db = SQLAlchemy(app)
    # reset serialize
    sr.serialize.all.CLASSES = {
        k: v
        for k, v in sr.serialize.all.CLASSES.items() if 'date' in str(k)
    }
    sr.serialize.all.CLASSES_BY_NAME = {
        k: v
        for k, v in sr.serialize.all.CLASSES_BY_NAME.items()
        if 'date' in str(k)
    }

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        birth_date = db.Column(db.Date)

        @property
        def id_to_text(self):
            return 'one'

        def age_in_x_years_y_months(self,
                                    y_offset,
                                    m_offset=0,
                                    *args,
                                    **kwargs):
            dt = self.birth_date
            return dt.replace(
                year=dt.year + y_offset, month=dt.month + m_offset)

        def get_attrs_based_on_dict(self, args):
            return_dict = {}
            for key, val in args.items():
                if val:
                    return_dict[key] = getattr(self, key)
            return return_dict

        def what_does_this_func_even_do(self, person):
            assert isinstance(person, Person)
            return person

    db.create_all()

    db.session.add(Person(name='Jim Darkmagic', birth_date=date(2018, 1, 1)))
    db.session.commit()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'])
    data_model = DataModel(manager, include_model_functions=True)
    manager.create_api(data_model, methods=['GET'])
    return app


def test_exposed_methods(exposed_method_model_app, client_maker):
    client = client_maker(exposed_method_model_app)
    res = client.get('http://app/api/flask-restless-datamodel').json()

    expected = {
        'Person': {
            'pk_name': 'id',
            'collection_name': 'person',
            'attributes': {
                'id': 'integer',
                'name': 'unicode',
                'birth_date': 'date',
            },
            'properties': {
                'id_to_text': 'property'
            },
            'relations': {},
            'methods': {
                'age_in_x_years_y_months': {
                    'args': ['y_offset'],
                    'kwargs': ['m_offset'],
                    'argsvar': 'args',
                    'kwargsvar': 'kwargs'
                },
                'get_attrs_based_on_dict': {
                    'args': ['args'],
                    'kwargs': [],
                    'argsvar': None,
                    'kwargsvar': None
                },
                'what_does_this_func_even_do': {
                    'args': ['person'],
                    'kwargs': [],
                    'argsvar': None,
                    'kwargsvar': None
                },
            }
        }
    }
    assert res == expected


def to_method_params(body):
    return {'payload': sr.dumps(body, fmt='msgpack')}


def test_call_exposed_method(exposed_method_model_app, client_maker):
    client = client_maker(exposed_method_model_app)
    url = 'http://app/api/method/person/1/age_in_x_years_y_months'
    body = to_method_params({
        'args': [],
        'kwargs': {
            'y_offset': 10,
            'm_offset': 3
        }
    })
    res = sr.loads(
        client.post(url, json=body).json()['payload'], fmt='msgpack')
    expected = date(2028, 4, 1)
    assert res == expected


def test_call_exposed_method_with_model(exposed_method_model_app,
                                        client_maker):
    client = client_maker(exposed_method_model_app)
    url = 'http://app/api/method/person/1/what_does_this_func_even_do'

    class Person:
        id = 1

    with patch('cereal_lazer.NAME_BY_CLASS') as NAME_BY_CLASS:
        NAME_BY_CLASS.__getitem__.return_value = 'Person'
        with patch('cereal_lazer.serialize.all.CLASSES') as CLASSES:
            CLASSES.items.return_value = [(Person, (lambda x: {'id': 1}, None))]
            body = to_method_params({
                'args': [],
                'kwargs': {
                    'person': Person()
                }
            })
    res = sr.loads(
        client.post(url, json=body).json()['payload'], fmt='msgpack')
    assert res.name == 'Jim Darkmagic'


def test_it_can_identify_a_hybrid_property(app, client_maker):
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        first_name = db.Column(db.Unicode)
        last_name = db.Column(db.Unicode)

        @hybrid_property
        def name(self):
            return "{} {}".format(self.first_name, self.last_name)

    db.create_all()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'])
    data_model = DataModel(manager)
    manager.create_api(data_model, methods=['GET'])

    expected = {
        'Person': {
            'attributes': {
                'first_name': 'unicode',
                'id': 'integer',
                'last_name': 'unicode',
                'name': 'hybrid'
            },
            'collection_name': 'person',
            'methods': {},
            'pk_name': 'id',
            'properties': {},
            'relations': {}
        }
    }

    client = client_maker(app)
    res = client.get('http://app/api/flask-restless-datamodel').json()
    assert res == expected


def test_it_can_identify_a_property(app, client_maker):
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        first_name = db.Column(db.Unicode)
        last_name = db.Column(db.Unicode)

        @hybrid_property
        def name(self):
            return "{} {}".format(self.first_name, self.last_name)

        @property
        def lower_name(self):
            return self.name.lower()

    db.create_all()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'])
    data_model = DataModel(manager)
    manager.create_api(data_model, methods=['GET'])

    expected = {
        'Person': {
            'attributes': {
                'first_name': 'unicode',
                'id': 'integer',
                'last_name': 'unicode',
                'name': 'hybrid',
            },
            'collection_name': 'person',
            'methods': {},
            'properties': {
                'lower_name': 'property'
            },
            'pk_name': 'id',
            'relations': {}
        }
    }

    client = client_maker(app)
    res = client.get('http://app/api/flask-restless-datamodel').json()
    assert res == expected


def test_it_can_get_a_property(exposed_method_model_app, client_maker):
    client = client_maker(exposed_method_model_app)
    url = 'http://app/api/property'

    class Person:
        id = 1

    with patch('cereal_lazer.NAME_BY_CLASS') as NAME_BY_CLASS:
        NAME_BY_CLASS.__getitem__.return_value = 'Person'
        with patch('cereal_lazer.serialize.all.CLASSES') as CLASSES:
            CLASSES.items.return_value = [(Person, (lambda x: {'id': 1}, None))]
            body = to_method_params({
                'object': Person(),
                'property': 'id_to_text'
            })
    res = sr.loads(
        client.post(url, json=body).json()['payload'], fmt='msgpack')
    assert res == 'one'
