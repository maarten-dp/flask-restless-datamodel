import inspect

import flask_restless
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm.attributes import QueryableAttribute


def primary_key_names(model):
    """Returns all the primary keys for a model."""
    return [
        key for key, field in inspect.getmembers(model)
        if isinstance(field, QueryableAttribute) and hasattr(
            field, 'property') and isinstance(field.property, ColumnProperty)
        and field.property.columns[0].primary_key
    ]


flask_restless.helpers.primary_key_names = primary_key_names
