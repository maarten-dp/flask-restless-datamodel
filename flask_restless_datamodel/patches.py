import inspect
import sys

import flask_restless
from pbr.version import SemanticVersion, VersionInfo


def primary_key_names(model):
    """Returns all the primary keys for a model."""
    return [
        key for key, field in inspect.getmembers(model)
        if isinstance(field, QueryableAttribute) and hasattr(
            field, 'property') and isinstance(field.property, ColumnProperty)
        and field.property.columns[0].primary_key
    ]


def get_related_model(model, relationname):
    """Gets the class of the model to which `model` is related by the attribute
    whose name is `relationname`.

    """
    if hasattr(model, relationname):
        attr = getattr(model, relationname)
        if hasattr(attr, 'property') \
                and isinstance(attr.property, RelProperty):
            return attr.property.mapper.class_
        if isinstance(attr, ASSOCIATION_PROXIES_KLASSES):
            return flask_restless.helpers.get_related_association_proxy_model(
                attr)
    return None


def get_relations(model):
    """Returns a list of relation names of `model` (as a list of strings)."""

    def is_accepted(k):
        return (not (k.startswith('__')
                     or k in flask_restless.helpers.RELATION_BLACKLIST)
                and not k.startswith("_AssociationProxy")
                and not k.startswith("_ReadOnlyAssociationProxy")
                and get_related_model(model, k))

    return [k for k in dir(model) if is_accepted(k)]


def is_like_list(instance, relation):
    """Returns ``True`` if and only if the relation of `instance` whose name is
    `relation` is list-like.

    A relation may be like a list if, for example, it is a non-lazy one-to-many
    relation, or it is a dynamically loaded one-to-many.

    """
    if relation in instance._sa_class_manager:
        return instance._sa_class_manager[relation].property.uselist
    elif hasattr(instance, relation):
        attr = getattr(instance._sa_instance_state.class_, relation)
        if hasattr(attr, 'property'):
            return attr.property.uselist
    related_value = getattr(type(instance), relation, None)
    if isinstance(related_value, ASSOCIATION_PROXIES_KLASSES):
        local_prop = related_value.local_attr.prop
        if isinstance(local_prop, RelProperty):
            return local_prop.uselist
    return False


def apply_patches():
    needs_patching = (primary_key_names, get_related_model, get_relations,
                      is_like_list)

    for func in needs_patching:
        funcname = func.__name__
        restless_mods = [
            m for m in sys.modules if m.startswith('flask_restless')
        ]
        for mod in restless_mods:
            if funcname in dir(sys.modules[mod]):
                setattr(sys.modules[mod], funcname, func)


sqla_version = VersionInfo('sqlalchemy').semantic_version()
if sqla_version >= SemanticVersion(1, 3, 0):
    from sqlalchemy.ext.associationproxy import (
        AssociationProxy, ObjectAssociationProxyInstance)
    from sqlalchemy.orm import (RelationshipProperty as RelProperty,
                                ColumnProperty)
    from sqlalchemy.orm.attributes import QueryableAttribute

    ASSOCIATION_PROXIES_KLASSES = (AssociationProxy,
                                   ObjectAssociationProxyInstance)
    apply_patches()
