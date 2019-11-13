[![Build Status](https://travis-ci.com/maarten-dp/flask-restless-datamodel.svg?branch=master)](https://travis-ci.com/maarten-dp/flask-restless-datamodel)
[![Codecov](https://codecov.io/gh/maarten-dp/flask-restless-datamodel/branch/master/graph/badge.svg)](https://codecov.io/gh/maarten-dp/flask-restless-datamodel)
[![PyPI version](https://badge.fury.io/py/flask-restless-datamodel.svg)](https://pypi.org/project/flask-restless-datamodel/)

## Purpose

This library is one part of a two part piece of code. It fulfills the server part to the flask-restless client. What it does is allow you to render your datamodel in a convenient JSON format.
This JSON format is then read by the flask-restless-client, which in turn uses it to built itself, allowing for transparent access to your data model through HTTP.

## Quickstart

Enabling this feature is as easy as registering an SQLAlchemy model in flask-restless. The only thing you need to do, is import the DataModel class from the library and use it to register your api.

```python
import flask
import flask_restless
from flask_sqlalchemy import SQLAlchemy
from flask_restless_datamodel import DataModel
from my_models import Person, Computer, db

app = flask.Flask(__name__)
db = SQLAlchemy(app)

# Create a datamodel instance to register later
data_model = DataModel(manager)

manager = flask_restless.APIManager(app, flask_sqlalchemy_db=db)
manager.create_api(Person, methods=['GET'], include_columns=['name'])
manager.create_api(Computer, methods=['GET'], collection_name='compjutahs', exclude_columns=['name'])
manager.create_api(data_model, methods=['GET'])
```

Which will expose an endpoint `http://localhost:5000/flask-restless-datamodel` which in turn will yield a result as followed

```json
{
   "Computer":{
      "attributes":{
         "id":"integer",
         "owner_id":"integer",
         "owner_name":"unicode",
         "purchase_time":"datetime",
         "vendor":"unicode"
      },
      "collection_name":"compjutahs",
      "methods":{},
      "pk_name":"id",
      "relations":{
         "owner":{
            "backref":"computers",
            "foreign_model":"Person",
            "local_column":"owner_id",
            "relation_type":"MANYTOONE"
         },
         "peers":{
            "foreign_model":"Computer",
            "is_proxy":true,
            "relation_type":"MANYTOONE"
         }
      }
   },
   "Person":{
      "attributes":{
         "name":"unicode"
      },
      "collection_name":"person",
      "methods":{},
      "pk_name":"id",
      "relations":{

      }
   }
}
```

This result will be used by the client code to build models on the fly.
