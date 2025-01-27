"""
PRIVATE MODULE: do not import (from) it directly.

This module contains functionality for loading stuff from json.
"""
import json
from json import JSONDecodeError
from typing import Optional, Dict, Callable, Tuple, Any
from jsons._lizers_impl import get_deserializer
from jsons.exceptions import DeserializationError, JsonsError, DecodeError
from jsons._common_impl import (
    StateHolder,
    get_cls_from_str,
    get_class_name,
    get_cls_and_meta,
    determine_precedence,
    VALID_TYPES)


def load(
        json_obj: object,
        cls: Optional[type] = None,
        strict: bool = False,
        fork_inst: Optional[type] = StateHolder,
        attr_getters: Optional[Dict[str, Callable[[], object]]] = None,
        **kwargs) -> object:
    """
    Deserialize the given ``json_obj`` to an object of type ``cls``. If the
    contents of ``json_obj`` do not match the interface of ``cls``, a
    DeserializationError is raised.

    If ``json_obj`` contains a value that belongs to a custom class, there must
    be a type hint present for that value in ``cls`` to let this function know
    what type it should deserialize that value to.


    **Example**:

    >>> from typing import List
    >>> import jsons
    >>> class Person:
    ...     # No type hint required for name
    ...     def __init__(self, name):
    ...         self.name = name
    >>> class Family:
    ...     # Person is a custom class, use a type hint
    ...         def __init__(self, persons: List[Person]):
    ...             self.persons = persons
    >>> loaded = jsons.load({'persons': [{'name': 'John'}]}, Family)
    >>> loaded.persons[0].name
    'John'

    If no ``cls`` is given, a dict is simply returned, but contained values
    (e.g. serialized ``datetime`` values) are still deserialized.

    If `strict` mode is off and the type of `json_obj` exactly matches `cls`
    then `json_obj` is simply returned.

    :param json_obj: the dict that is to be deserialized.
    :param cls: a matching class of which an instance should be returned.
    :param strict: a bool to determine if the deserializer should be strict
    (i.e. fail on a partially deserialized `json_obj` or on `None`).
    :param fork_inst: if given, it uses this fork of ``JsonSerializable``.
    :param attr_getters: a ``dict`` that may hold callables that return values
    for certain attributes.
    :param kwargs: the keyword args are passed on to the deserializer function.
    :return: an instance of ``cls`` if given, a dict otherwise.
    """
    if _should_skip(json_obj, cls, strict):
        return json_obj
    if isinstance(cls, str):
        cls = get_cls_from_str(cls, json_obj, fork_inst)
    cls, meta_hints = _check_and_get_cls_and_meta_hints(
        json_obj, cls, fork_inst, kwargs.get('_inferred_cls', False))

    deserializer = get_deserializer(cls, fork_inst)
    kwargs_ = {
        'strict': strict,
        'fork_inst': fork_inst,
        'attr_getters': attr_getters,
        'meta_hints': meta_hints,
        **kwargs
    }
    try:
        return deserializer(json_obj, cls, **kwargs_)
    except Exception as err:
        if isinstance(err, JsonsError):
            raise
        raise DeserializationError(str(err), json_obj, cls)


def loads(
        str_: str,
        cls: Optional[type] = None,
        jdkwargs: Optional[Dict[str, object]] = None,
        *args,
        **kwargs) -> object:
    """
    Extend ``json.loads``, allowing a string to be loaded into a dict or a
    Python instance of type ``cls``. Any extra (keyword) arguments are passed
    on to ``json.loads``.

    :param str_: the string that is to be loaded.
    :param cls: a matching class of which an instance should be returned.
    :param jdkwargs: extra keyword arguments for ``json.loads`` (not
    ``jsons.loads``!)
    :param args: extra arguments for ``jsons.loads``.
    :param kwargs: extra keyword arguments for ``jsons.loads``.
    :return: a JSON-type object (dict, str, list, etc.) or an instance of type
    ``cls`` if given.
    """
    jdkwargs = jdkwargs or {}
    try:
        obj = json.loads(str_, **jdkwargs)
    except JSONDecodeError as err:
        raise DecodeError('Could not load a dict; the given string is not '
                          'valid JSON.', str_, cls, err)
    else:
        return load(obj, cls, *args, **kwargs)


def loadb(
        bytes_: bytes,
        cls: Optional[type] = None,
        encoding: str = 'utf-8',
        jdkwargs: Optional[Dict[str, object]] = None,
        *args,
        **kwargs) -> object:
    """
    Extend ``json.loads``, allowing bytes to be loaded into a dict or a Python
    instance of type ``cls``. Any extra (keyword) arguments are passed on to
    ``json.loads``.

    :param bytes_: the bytes that are to be loaded.
    :param cls: a matching class of which an instance should be returned.
    :param encoding: the encoding that is used to transform from bytes.
    :param jdkwargs: extra keyword arguments for ``json.loads`` (not
    ``jsons.loads``!)
    :param args: extra arguments for ``jsons.loads``.
    :param kwargs: extra keyword arguments for ``jsons.loads``.
    :return: a JSON-type object (dict, str, list, etc.) or an instance of type
    ``cls`` if given.
    """
    if not isinstance(bytes_, bytes):
        raise DeserializationError('loadb accepts bytes only, "{}" was given'
                                   .format(type(bytes_)), bytes_, cls)
    jdkwargs = jdkwargs or {}
    str_ = bytes_.decode(encoding=encoding)
    return loads(str_, cls, jdkwargs=jdkwargs, *args, **kwargs)


def _check_and_get_cls_and_meta_hints(
        json_obj: object,
        cls: type,
        fork_inst: type,
        inferred_cls: bool) -> Tuple[type, Optional[dict]]:
    # Check if json_obj is of a valid type and return the cls.
    if type(json_obj) not in VALID_TYPES:
        invalid_type = get_class_name(type(json_obj), fork_inst=fork_inst,
                                      fully_qualified=True)
        valid_types = [get_class_name(typ, fork_inst=fork_inst,
                                      fully_qualified=True)
                       for typ in VALID_TYPES]
        msg = ('Invalid type: "{}", only arguments of the following types are '
               'allowed: {}'.format(invalid_type, ", ".join(valid_types)))
        raise DeserializationError(msg, json_obj, cls)
    if json_obj is None:
        raise DeserializationError('Cannot load None with strict=True',
                                   json_obj, cls)

    cls_from_meta, meta = get_cls_and_meta(json_obj, fork_inst)
    meta_hints = meta.get('classes', {}) if meta else {}
    return determine_precedence(
        cls, cls_from_meta, type(json_obj), inferred_cls), meta_hints


def _should_skip(json_obj: object, cls: type, strict: bool):
    if not strict:
        if json_obj is None or type(json_obj) == cls:
            return True
    if cls is Any:
        return True
