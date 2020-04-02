from datetime import date
from unittest.mock import patch

import flask_restless
import pytest
from cereal_lazer import Cereal
from flask_restless_datamodel import DataModel, __version__
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
        'FlaskRestlessDatamodel': {
            'server_version': __version__,
            'serialize_naively': False,
        },
        'Computer': {
            'pk_name': 'id',
            'collection_name': 'compjutahs',
            'url_prefix': '/api',
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
            'url_prefix': '/api',
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
        'FlaskRestlessDatamodel': {
            'server_version': __version__,
            'serialize_naively': False,
        },
        'Engineer': {
            'pk_name': 'id',
            'collection_name': 'engineer',
            'url_prefix': '/api',
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
            'url_prefix': '/api',
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
    return _exposed_method_model_app(app)


@pytest.fixture(scope='function')
def exposed_method_model_app_with_commit(app):
    return _exposed_method_model_app(app, commit_before_return=True)


def _exposed_method_model_app(app, commit_before_return=False):
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        birth_date = db.Column(db.Date)

        @property
        def id_to_text(self):
            return 'one'

        @property
        def settable_property(self):
            return self.name

        @settable_property.setter
        def settable_property(self, value):
            self.name = value

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

        def raise_an_error(self):
            raise Exception('Something happened')

        def create_person_but_dont_commit(self):
            person = Person(name='Some dude')
            db.session.add(person)
            db.session.flush()
            return person

    app.Person = Person
    db.create_all()

    db.session.add(Person(name='Jim Darkmagic', birth_date=date(2018, 1, 1)))
    db.session.commit()

    manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['GET'])
    data_model = DataModel(
        manager,
        include_model_functions=True,
        commit_on_method_return=commit_before_return)
    manager.create_api(data_model, methods=['GET'])
    return app


def test_exposed_methods(exposed_method_model_app, client_maker):
    client = client_maker(exposed_method_model_app)
    res = client.get('http://app/api/flask-restless-datamodel').json()

    expected = {
        'FlaskRestlessDatamodel': {
            'server_version': __version__,
            'serialize_naively': False,
        },
        'Person': {
            'pk_name': 'id',
            'collection_name': 'person',
            'url_prefix': '/api',
            'attributes': {
                'id': 'integer',
                'name': 'unicode',
                'birth_date': 'date',
            },
            'properties': {
                'id_to_text': False,
                'settable_property': True
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
                'raise_an_error': {
                    'args': [],
                    'kwargs': [],
                    'argsvar': None,
                    'kwargsvar': None
                },
                'create_person_but_dont_commit': {
                    'args': [],
                    'kwargs': [],
                    'argsvar': None,
                    'kwargsvar': None
                },
            }
        }
    }
    assert res == expected


def to_method_params(body, sr):
    return {'payload': sr.dumps(body)}


def test_call_exposed_method(exposed_method_model_app, client_maker):
    client = client_maker(exposed_method_model_app)
    sr = exposed_method_model_app.extensions['cereal']
    url = 'http://app/api/method/person/1/age_in_x_years_y_months'
    body = to_method_params({
        'args': [],
        'kwargs': {
            'y_offset': 10,
            'm_offset': 3
        }
    }, sr)
    res = sr.loads(client.post(url, json=body).json()['payload'])
    expected = date(2028, 4, 1)
    assert res == expected


def test_call_exposed_method_raises_an_error(exposed_method_model_app,
                                             client_maker):
    client = client_maker(exposed_method_model_app)
    url = 'http://app/api/method/person/1/raise_an_error'
    sr = exposed_method_model_app.extensions['cereal']
    body = to_method_params({'args': [], 'kwargs': {}}, sr)

    res = client.post(url, json=body)
    assert res.status_code == 500
    assert res.json() == {'message': 'Exception: Something happened'}


def test_call_exposed_method_with_model(exposed_method_model_app,
                                        client_maker):
    client = client_maker(exposed_method_model_app)
    url = 'http://app/api/method/person/1/what_does_this_func_even_do'
    sr = exposed_method_model_app.extensions['cereal']
    client_cereal = Cereal()

    class Person:
        id = 1

    client_cereal.register_class('Person', Person, lambda x: {'id': x.id},
                                 lambda x: x)

    body = to_method_params({
        'args': [],
        'kwargs': {
            'person': Person()
        }
    }, client_cereal)
    res = sr.loads(client.post(url, json=body).json()['payload'])
    assert res.name == 'Jim Darkmagic'


def run_transient_method(client, status, sr):
    url = 'http://app/api/method/person/1/create_person_but_dont_commit'
    body = to_method_params({'args': [], 'kwargs': {}}, sr)
    client_cereal = Cereal()
    client_cereal.register_class('Person', None, None, lambda x: x)

    res = client_cereal.loads(client.post(url, json=body).json()['payload'])
    assert res == {'id': 2, 'name': 'Some dude', 'birth_date': None}

    url = 'http://app/api/person/2'
    assert client.get(url).status_code == status


def test_it_doesnt_commit_transient_objects(exposed_method_model_app,
                                            client_maker):
    client = client_maker(exposed_method_model_app)
    sr = exposed_method_model_app.extensions['cereal']
    run_transient_method(client, 404, sr)


def test_it_commits_transient_objects(exposed_method_model_app_with_commit,
                                      client_maker):
    client = client_maker(exposed_method_model_app_with_commit)
    sr = exposed_method_model_app_with_commit.extensions['cereal']
    run_transient_method(client, 200, sr)


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
        'FlaskRestlessDatamodel': {
            'server_version': __version__,
            'serialize_naively': False,
        },
        'Person': {
            'attributes': {
                'first_name': 'unicode',
                'id': 'integer',
                'last_name': 'unicode',
                'name': 'hybrid'
            },
            'collection_name': 'person',
            'url_prefix': '/api',
            'methods': {},
            'pk_name': 'id',
            'properties': {},
            'relations': {},
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
        'FlaskRestlessDatamodel': {
            'server_version': __version__,
            'serialize_naively': False,
        },
        'Person': {
            'attributes': {
                'first_name': 'unicode',
                'id': 'integer',
                'last_name': 'unicode',
                'name': 'hybrid',
            },
            'collection_name': 'person',
            'url_prefix': '/api',
            'methods': {},
            'properties': {
                'lower_name': False
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
    url = 'http://app/api/property/person/1/id_to_text'
    sr = exposed_method_model_app.extensions['cereal']
    res = sr.loads(client.get(url).json()['payload'])
    assert res == 'one'


def test_it_can_set_a_property(exposed_method_model_app, client_maker):
    app = exposed_method_model_app
    client = client_maker(app)
    url = 'http://app/api/property/person/1/settable_property'
    sr = app.extensions['cereal']
    expected = 'new_value'

    body = sr.dumps(expected)
    res = client.post(url, json=body)
    person = app.Person.query.get(1)
    assert person.name == expected
