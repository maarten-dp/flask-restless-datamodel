import inspect

from flask_restless.helpers import get_related_association_proxy_model, primary_key_name
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.inspection import inspect as sqla_inspect
from sqlalchemy.orm.properties import ColumnProperty, RelationshipProperty

from .helpers import object_property, register_serializer, run_object_method

INCLUDE_INTERNAL = 'include_model_internal_functions'
COMMIT_ON_RETURN = 'commit_on_method_return'
EXPOSE_PROPERTY = 'expose_property'


def clean(columns):
    return columns or []


def get_is_valid_validator(included, excluded):
    def is_valid(column):
        column = column.split('.')[-1]
        valid_excl = True
        valid_incl = True
        if excluded:
            valid_excl = column not in excluded
        if included:
            valid_incl = column in included
        return valid_excl and valid_incl

    return is_valid


def is_polymorphic(model, check_var):
    has_mapper_args = hasattr(model, '__mapper_args__')
    if has_mapper_args and check_var in model.__mapper_args__:
        return True
    return False


class DataModelRenderer:
    def __init__(self, app, db, options):
        self.app = app
        self.options = options

    def render(self, model, config):
        klass = ClassDefinitionRenderer(self.app, self.options, model, config)
        methods = MethodDefinitionRenderer(self.options, model, config)
        model_render = klass.render()
        model_render['methods'] = methods.render()
        return model_render

    def render_polymorphic(self, model, identities):
        polymorphic_info = {}
        if is_polymorphic(model, 'polymorphic_on'):
            mapper_args = model.__mapper_args__
            on = mapper_args['polymorphic_on']
            if not isinstance(on, str):
                on = on.key
            polymorphic_info['on'] = on
            polymorphic_info['identities'] = identities
        if is_polymorphic(model, 'polymorphic_identity'):
            mapper_args = model.__mapper_args__
            for kls in model.__bases__:
                if is_polymorphic(kls, 'polymorphic_on'):
                    polymorphic_info['parent'] = kls.__name__
                    polymorphic_info['identity'] = mapper_args[
                        'polymorphic_identity']
        return polymorphic_info


class ClassDefinitionRenderer:
    def __init__(self, app, options, model, config):
        self.app = app
        self.model = model
        self.options = options
        self.config = config
        self.is_valid = get_is_valid_validator(
            clean(config.view.include_columns),
            clean(config.view.exclude_columns))

    def render(self):
        view = self.config.view
        collection_name = self.config.collection_name

        attribute_dict = self.render_attributes()
        foreign_keys = self.render_relations()
        properties = {}
        if self.options.get(EXPOSE_PROPERTY, True):
            properties = self.render_properties()
        attribute_dict.update(self.render_hybrid_properties())
        self.render_association_proxies(attribute_dict, foreign_keys)

        with self.app.app_context():
            pk_name = primary_key_name(self.model)

        cr = self.app.extensions['cereal']
        register_serializer(self.model, pk_name, view.serialize,
                            view.deserialize, cr)

        return {
            'pk_name': pk_name,
            'collection_name': collection_name,
            'url_prefix': self.config.blueprint.url_prefix,
            'attributes': attribute_dict,
            'relations': foreign_keys,
            'properties': properties,
        }

    def render_attributes(self):
        attribute_dict = {}
        for column in sqla_inspect(self.model).columns:
            if self.is_valid(column.name):
                ctype = column.type.__class__.__name__.lower()
                attribute_dict[column.name] = ctype
        return attribute_dict

    def render_relations(self):
        foreign_keys = {}
        for rel in sqla_inspect(self.model).relationships:
            if self.is_valid(str(rel.key)):
                direction = rel.direction.name
                if rel.direction.name == 'ONETOMANY' and not rel.uselist:
                    direction = 'ONETOONE'
                foreign_keys[rel.key] = {
                    'foreign_model': rel.mapper.class_.__name__,
                    'relation_type': direction,
                    'backref': rel.back_populates,
                }
                if rel.direction.name == 'MANYTOONE':
                    local_id = list(rel.local_columns)[0].key
                    foreign_keys[rel.key]['local_column'] = local_id
        return foreign_keys

    def render_properties(self):
        attribute_dict = {}
        properties = [(a, getattr(self.model, a).fset is not None)
                      for a in dir(self.model)
                      if isinstance(getattr(self.model, a), property)]
        for attribute, settable in properties:
            if self.is_valid(attribute):
                self.add_property_endpoint(attribute)
                attribute_dict[attribute] = settable

        return attribute_dict

    def render_hybrid_properties(self):
        attribute_dict = {}
        hybrid_properties = [
            a for a in sqla_inspect(self.model).all_orm_descriptors
            if isinstance(a, hybrid_property)
        ]
        for attribute in hybrid_properties:
            name = attribute.__name__
            if self.is_valid(name):
                attribute_dict[name] = 'hybrid'
        return attribute_dict

    def render_association_proxies(self, attribute_dict, foreign_keys):
        proxies = {}
        for k in list(self.model.__dict__.keys()):
            v = self.model.__dict__[k]
            is_proxy = isinstance(v, AssociationProxy)
            # keep the proxies where the remote attr has a property,
            # as we need this property to identify the remote class
            # but not all cases have it.
            # v == v.__get__(None, model), but we do this to bind the model to
            # the remote_attr and from then on it's usable for further inspection
            if is_proxy and hasattr(
                    v.__get__(None, self.model).remote_attr, 'property'):
                proxies[k] = v.__get__(None, self.model)

        for name, attr in proxies.items():
            # check if the remote attr is a relation (for example, an association
            # table) or if it's an attribute
            if isinstance(attr.remote_attr.property, RelationshipProperty):
                # use the helper function from flask restless to identify the
                # remote class
                remote_class = get_related_association_proxy_model(attr)
                foreign_keys[name] = {
                    'foreign_model': remote_class.__name__,
                    'relation_type': 'MANYTOONE'
                                     if attr.scalar else 'ONETOMANY',
                    'is_proxy': True
                }
            elif isinstance(attr.remote_attr.property, ColumnProperty):
                # The columns of remote attr will always be 1 element in size
                # as the columns is refering to itself (i.e. the remote attr)
                column = attr.remote_attr.property.columns[0]
                attribute_dict[name] = column.type.__class__.__name__.lower()

    def add_property_endpoint(self, property_name):
        fmt = '/property/{0}/<instid>/{1}'
        endpoint = fmt.format(self.config.collection_name, property_name)
        self.config.blueprint.add_url_rule(
            endpoint,
            methods=['GET', 'POST'],
            defaults={
                'model': self.model,
                'property_name': property_name
            },
            view_func=object_property)


class MethodDefinitionRenderer:
    def __init__(self, options, model, config):
        self.options = options
        self.model = model
        self.config = config

    def render(self):
        methods = self.compile_method_list()
        self.add_method_endpoints(methods)
        return methods

    def compile_method_list(self):
        methods = {}
        include_internal = self.options.get(INCLUDE_INTERNAL, False)
        for name, fn in inspect.getmembers(
                self.model, predicate=inspect.isfunction):
            if name.startswith('__'):
                continue
            if name.startswith('_') and not include_internal:
                continue

            spec = inspect.signature(fn)
            required = []
            optional = []
            argsvar = None
            kwargsvar = None
            for param_name, param in spec.parameters.items():
                if param_name == 'self':
                    continue
                if param.kind == param.VAR_KEYWORD:
                    kwargsvar = param_name
                elif param.kind == param.VAR_POSITIONAL:
                    argsvar = param_name
                elif param.default == param.empty:
                    required.append(param_name)
                else:
                    optional.append(param_name)

            methods[name] = {
                'args': required,
                'kwargs': optional,
                'argsvar': argsvar,
                'kwargsvar': kwargsvar,
            }
        return methods

    def add_method_endpoints(self, methods):
        commit_on_return = self.options.get(COMMIT_ON_RETURN, False)
        collection_name = self.config.collection_name
        for method in methods.keys():
            fmt = '/method/{0}/<instid>/{1}'
            instance_endpoint = fmt.format(collection_name, method)
            self.config.blueprint.add_url_rule(
                instance_endpoint,
                methods=['POST'],
                defaults={
                    'function_name': method,
                    'model': self.model,
                    'commit_on_return': commit_on_return,
                },
                view_func=run_object_method)
